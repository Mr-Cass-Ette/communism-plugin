import logging
import pwnagotchi.plugins as plugins
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import os
import shutil
import subprocess
import random
import threading
import time
from ftplib import FTP
from collections import defaultdict
from pyftpdlib.servers import FTPServer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.authorizers import DummyAuthorizer
mode=2

#mode = 1 → Full sync (all files)
#mode = 2 → Smart sync (only largest file per prefix group)

#failsafe to prevent transferring multiple times in a single day
import datetime
import os
def failsafe(filename="failsafe.txt", name=None, mode="write"):
    """
    Failsafe function with two modes:
    
    1. mode="write": writes the given name and today's date into a file.
    2. mode="check": checks if the file contains the same name and today's date.
    
    Args:
        filename (str): file to write to/read from.
        name (str): the name to write or check.
        mode (str): "write" or "check".
    
    Returns:
        bool: True if check passes (only in "check" mode), False otherwise.
    """
    today = datetime.date.today().isoformat()
    
    if mode == "write":
        if not name:
            raise ValueError("Name must be provided in write mode.")
        with open(filename, "w") as f:
            f.write(f"{name},{today}")
        return True
    
    elif mode == "check":
        if not os.path.exists(filename):
            return False
        with open(filename, "r") as f:
            content = f.read().strip()
        expected = f"{name},{today}"
        return content == expected
    
    else:
        raise ValueError("Mode must be either 'write' or 'check'.")

#command for executing when number=0
def _host_ftp(ssid="Dealbreaker", password="PTWwohrnled!",
             interface="wlan0", ftp_user="user", ftp_pass="12345",
             ftp_dir="/home/pi", ftp_port=21, idle_timeout=300):

    active_connections = {"count": 0}
    idle_timer = {"timer": None}

    def shutdown_hotspot():
        subprocess.run(["sudo", "systemctl", "stop", "hostapd"])
        subprocess.run(["sudo", "systemctl", "stop", "dnsmasq"])
        _log("Hotspot services stopped.")

    def schedule_idle_shutdown():
        """Restart idle timer."""
        if idle_timer["timer"]:
            idle_timer["timer"].cancel()
        idle_timer["timer"] = threading.Timer(idle_timeout, shutdown_due_to_idle)
        idle_timer["timer"].start()

    def shutdown_due_to_idle():
        if active_connections["count"] <= 0:
            _log(f"No activity for {idle_timeout} seconds. Shutting down server and hotspot...")
            server.close_all()
            shutdown_hotspot()

    class CustomHandler(FTPHandler):
        def on_connect(self):
            active_connections["count"] += 1
            _log(f"Client connected. Active: {active_connections['count']}")
            if idle_timer["timer"]:
                idle_timer["timer"].cancel()  # stop idle shutdown while active

        def on_disconnect(self):
            active_connections["count"] -= 1
            _log(f"Client disconnected. Active: {active_connections['count']}")
            if active_connections["count"] <= 0:
                schedule_idle_shutdown()  # restart idle timer

    def setup_hotspot():
        hostapd_conf = f"""
interface={interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
"""
        with open("/etc/hostapd/hostapd.conf", "w") as f:
            f.write(hostapd_conf)

        subprocess.run(["sudo", "sed", "-i",
                        "s|#DAEMON_CONF=.*|DAEMON_CONF=\"/etc/hostapd/hostapd.conf\"|",
                        "/etc/default/hostapd"], check=True)

        dnsmasq_conf = f"""
interface={interface}
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
"""
        with open("/etc/dnsmasq.conf", "w") as f:
            f.write(dnsmasq_conf)

        subprocess.run(["sudo", "ifconfig", interface, "192.168.4.1"], check=True)
        subprocess.run(["sudo", "systemctl", "restart", "hostapd"], check=True)
        subprocess.run(["sudo", "systemctl", "restart", "dnsmasq"], check=True)

        _log(f"Hotspot {ssid} active. Password: {password}")
        _log("Pi reachable at 192.168.4.1")

    # --- Setup Hotspot ---
    setup_hotspot()

    # --- Setup FTP ---
    authorizer = DummyAuthorizer()
    authorizer.add_user(ftp_user, ftp_pass, ftp_dir, perm="elradfmw")

    handler = CustomHandler
    handler.authorizer = authorizer

    global server
    server = FTPServer(("0.0.0.0", ftp_port), handler)
    _log(f"FTP server running at 192.168.4.1:{ftp_port} (user={ftp_user})")

    # Start idle shutdown timer immediately (no clients yet)
    schedule_idle_shutdown()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("Manual shutdown requested. Closing hotspot.")
        shutdown_hotspot()

#command for executing when number=1
def _sync_via_FTP(mode=mode, ssid="Dealbreaker", password="PTWwohrnled!",
                      ftp_host="192.168.4.1", ftp_user="user", ftp_pass="12345", interface="wlan0", ftp_dir="/home/pi", ftp_port=21):
    """
    mode = 1 → Full sync (all files)
    mode = 2 → Smart sync (only largest file per prefix group)
    """
    # Disconnect from any pre-connected Wi-Fi
    try:
        subprocess.run(["nmcli", "d", "disconnect", "wlan0"], check=True)
        _log("Wi-Fi disconnected.")
    except Exception as e:
        _log(f"⚠️ Could not disconnect Wi-Fi: {e}")

    # --- Step 1: Ensure we are connected to the Wi-Fi ---
    try:
        subprocess.run(["nmcli", "d", "wifi", "connect", ssid, "password", password],
                       check=True)
        _log(f"Connected to {ssid}")
    except Exception as e:
        _log(f"⚠️ Wi-Fi connect failed (maybe already connected?): {e}")

    # --- Step 2: Connect to FTP server ---
    ftp = FTP()
    ftp.connect(ftp_host, 21)
    ftp.login(ftp_user, ftp_pass)
    _log("Connected to FTP server.")

    local_demo = "/home/pi/handshakes"
    local_temp = "/home/pi/temp-shakes"
    os.makedirs(local_demo, exist_ok=True)
    os.makedirs(local_temp, exist_ok=True)

    ftp.cwd("/home/pi/handshakes")

    # --- Decide which files to transfer ---
    if mode == 1:
        # Full sync
        files_to_transfer = ftp.nlst()

    elif mode == 2:
        # Smart sync: get file sizes, group by prefix, pick largest
        grouped = defaultdict(list)
        for fname in ftp.nlst():
            try:
                size = ftp.size(fname)
            except Exception:
                size = 0
            prefix = fname.split("_")[0]
            grouped[prefix].append((fname, size))

        files_to_transfer = []
        for prefix, items in grouped.items():
            # pick file with max size
            best = max(items, key=lambda x: x[1])[0]
            files_to_transfer.append(best)

        _log(f"Smart sync selected files: {files_to_transfer}")

    else:
        ftp.quit()
        raise ValueError("Mode must be 1 (full) or 2 (smart)")

    # --- Step 2.1: FTP:/home/pi/handshakes -> SELF:/home/pi/temp-shakes ---
    for fname in files_to_transfer:
        local_path = os.path.join(local_temp, fname)
        with open(local_path, "wb") as f:
            ftp.retrbinary(f"RETR {fname}", f.write)
        _log(f"Downloaded {fname} -> {local_path}")

    # --- Step 2.2: SELF:/home/pi/handshakes -> FTP:/home/pi/handshakes ---
    for fname in os.listdir(local_demo):
        local_path = os.path.join(local_demo, fname)
        if os.path.isfile(local_path):
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {fname}", f)
            _log(f"Uploaded {local_path} -> FTP:/home/pi/handshakes/{fname}")

    # --- Step 2.3: SELF:/home/pi/temp-shakes -> SELF:/home/pi/handshakes ---
    for fname in os.listdir(local_temp):
        src = os.path.join(local_temp, fname)
        dst = os.path.join(local_demo, fname)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            _log(f"Copied {src} -> {dst}")

    ftp.quit()
    _log("Sync complete ✅")
    # Disconnect from Wi-Fi
    try:
        subprocess.run(["nmcli", "d", "disconnect", "wlan0"], check=True)
        _log("Wi-Fi disconnected.")
    except Exception as e:
        _log(f"⚠️ Could not disconnect Wi-Fi: {e}")

def _disable_monitor_mode(self, agent):
    _log('sending command to Bettercap to stop using mon0...')
    self.status = 'switching_mon_off'
    agent.run('wifi.recon off')
    _log('ensuring all wpa_supplicant processes are terminated...')
    subprocess.run('systemctl stop wpa_supplicant; killall wpa_supplicant', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    _log('disabling monitor mode...')
    subprocess.run('modprobe --remove brcmfmac; modprobe brcmfmac', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    # Runs this driver reload command again because sometimes it gets stuck the first time:
    subprocess.run('modprobe --remove brcmfmac; modprobe brcmfmac', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    _log('randomizing wlan0 MAC address prior to connecting...')
    self.status = 'scrambling_mac'
    subprocess.run('macchanger -A wlan0', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    _log('starting up wlan0 again...')
    subprocess.run('ifconfig wlan0 up', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(3)
    # This command runs multiple times because it sometimes doesn't work the first time:
    subprocess.run('ifconfig wlan0 up', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
 
def _restart_monitor_mode(self,agent):
    _log('resuming wifi recon and monitor mode...')
    _log('stopping wpa_supplicant...')
    subprocess.run('systemctl stop wpa_supplicant; killall wpa_supplicant', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    _log('reloading brcmfmac driver...')
    subprocess.run('modprobe --remove brcmfmac && modprobe brcmfmac', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    _log('randomizing MAC address of wlan0...')
    subprocess.run('macchanger -A wlan0', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    time.sleep(5)
    subprocess.run('ifconfig wlan0 up', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    _log('starting monitor mode...')
    subprocess.run('iw phy "$(iw phy | head -1 | cut -d" " -f2)" interface add mon0 type monitor && ifconfig mon0 up', shell=True, stdin=None, stdout=open("/dev/null", "w"), stderr=None, executable="/bin/bash")
    _log('telling Bettercap to resume wifi recon...')
    agent.run('wifi.recon on')
    agent.next_epoch(self)


def _hijack(self, agent):
        """override the necessary functions to make pwnagotchi stop pwning for a while"""
        try:

            # this is the replacement function
            def hj_observe(self, aps, peers):
                """ Epoch.observe() sets the blind_for and inactive_for, which trigger
                    actions that should be avoided while recon is disabled
                    Override Epoch.observe() with hj_observe, which calls the original,
                    then sets those stats to be 0.  Also sets num_missed so is_stale()
                    will be true and attacks get skipped."""
                logging.debug("HJ observe: %s, %s, %s" % (self, len(aps), len(peers)))
                try:
                    if hasattr(self, 'hj_funcs'):   # if this object has been hijacked
                        o_func = self.hj_funcs.get('observe', None)  # get original function from dictionary
                        if o_func:
                            o_func(aps, peers)    # call real observe function, pwnagotchi.ai.epoch.observe()
                        # override some of the stats
                        if self.blind_for > 0:
                            logging.warn("Resetting blind count from %d" % (self.blind_for))
                            self.blind_for = 0
                        if self.inactive_for > 0:
                            logging.warn("Resetting inactive count from %d" % (self.inactive_for))
                            self.inactive_for = 0
                        if self.sad_for > 0:
                            logging.warn("Resetting sad count from %d" % (self.sad_for))
                            self.sad_for = 0
                        if self.bored_for > 0:
                            logging.warn("Resetting bored count from %d" % (self.bored_for))
                            self.bored_for = 0
                        # set high enough to be stale, so attacks get skipped
                        self.num_missed = self.config['personality']['max_misses_for_recon'] + 1
                    else:
                        logging.error("ep has no orig_observe: %s" % (repr(self)))
                except Exception as e:
                    logging.exception(e)

            # and this is how it gets installed:
            ep = agent._epoch
            if ep:

                # add a dictionary to the object, to keep track of original functions
                # so they can be restored in on_unload
                if hasattr(ep, 'hj_funcs'):
                    logging.error("Already hijacked. wtf?")
                else:
                    ep.hj_funcs = {}

                # save the origional. Do not overwrite if one is already saved (since that's the OG original)
                if not 'observe' in ep.hj_funcs:
                    ep.hj_funcs['observe'] = ep.observe

                # override the Epoch.observe function with hj_observe
                ep.observe = hj_observe.__get__(ep, Epoch)
                logging.info("Hijacked recon functions %s" % (ep.hj_funcs))

            # finally disable attacks and switch off bettercap recon
            try:
                # set num_missed to avoid attacks
                ep.num_missed = ep.config['personality']['max_misses_for_recon'] + 1

                # pause recon in bettercap
                r = agent.run('wifi.recon off')
                logging.info("Wifi recon off: %s" % (r))
            except Exception as e:
                logging.error("Disabling recon: %s" % (e))
        except Exception as e:
            logging.exception(e)

def _un_hijack(self, agent):
        """ restore original functions and operation """
        try:
            if not agent:
                logging.info("No agent")
                return
            ep = agent._epoch
            
            logging.info("Unjacking %s" % (ep))
            if hasattr(ep, 'hj_funcs'):
                # restore the observe function
                ep.observe = ep.hj_funcs['observe']
                if ep.observe == ep.hj_funcs['observe']:    # verify that it was restored
                    logging.info("Restored Epoch.observe")
                    del ep.hj_funcs['observe']
                else:
                    logging.error("Failed to restore observe function")

                # leave no trace
                del ep.hj_funcs
            else:
                logging.error("\t\t\tNothing to unjack")

            try:
                ep.num_missed = 0   # set to 0, so attacks activate again

                # restart wifi.recon in bettercap
                r = agent.run('wifi.recon on')
                logging.info("Wifi recon on: %s" % (r))
            except Exception as e:
                logging.error("Enabling recon: %s" % (e))
        except Exception as e:
            logging.exception(e)


def _log(message):
    logging.info('[Communism] %s' % message)

class Communism(plugins.Plugin):
    __author__ = 'Mr. Cass Ette'
    __version__ = '1.0.0'
    __license__ = 'GPL3'
    __description__ = 'WIP - A plugin for pwnagotchi that sends handshakes to peers (Same thing communism tried)'

    def __init__(self):
        self.action_number = None

    def send(message):
        logging.info("placeholder")
# TODO: Create working send function to send between peers
    def listen():
        logging.info("placeholder")
#TODO: Create working listen function to wait for the most recent message sent from peer


    def assign(self, max_retries=5):
        """
        Generates a unique number (0 or 1) that differs from the peer's.
        Stores it in self.action_number.
        """
        self.action_number = random.randint(0, 1)
        retries = 0

        while retries < max_retries:
            try:
                self.send(str(self.action_number))  # Send our number
                time.sleep(0.5)            # Allow time for the other client

                other_number_raw = self.listen()
                if other_number_raw is None:
                    retries += 1
                    continue

                other_number = int(other_number_raw)

                if self.action_number != other_number:
                    return  # Success: self.action_number is now unique
                else:
                    self.action_number = 1 - self.action_number  # Flip the bit
                    retries += 1
                    time.sleep(0.5)
            except Exception as e:
                logging.info(f"Communication error: {e}")
                retries += 1

        logging.debug("Failed to assign a unique number after several retries.")
        self.action_number = 2
    

    # called when the plugin is loaded
    def on_loaded(self):
        logging.debug("[Communism] Plugin Loaded")

    # called before the plugin is unloaded
    def on_unload(self, ui):
        pass

    # called hen there's internet connectivity
    def on_internet_available(self, agent):
        pass

    # called when everything is ready and the main loop is about to start
    def on_ready(self, agent):
        logging.info("unit is ready")

    # called when a new peer is detected
    def on_peer_detected(self, agent, peer):
        #insert ftp setup here
        #self.ui.update(force=True, new_data={'status': f'Found a fellow Commie! Communicating FTP protocal...', 'face': '(•‿‿•)'}) # (# of handshakes sent / # of total handshakes)
        if failsafe(name=peer, mode="check"):
            _log("Already connected to peer")
            #self.ui.update(force=False, new_data={'status': f'We already talked today, {peer}...', 'face': f"(-_-')"})
        else:
            _hijack(self, agent)
            self.assign()
            if self.action_number == 0:
                logging.info("HOST FTP SERVER")
                #self.ui.update(force=True, new_data={'status': f'Hosting the FTP server, {peer} is responsible for transferring files...', 'face': '(•‿•)🍺'})
                _host_ftp()
            elif self.action_number == 1:
                logging.info("CONNECT TO FTP & MOVE FILES")
                #self.ui.update(force=True, new_data={'status': f'Connecting to FTP server, {peer} is responsible for hosting...', 'face': '🍺(•‿•)'})
                _sync_via_FTP()
            else:
                #self.ui.update(force=True, new_data={'status': f'We lost {peer} to The Reds! (No Communism Plugin)'})
                logging.info("Peer returned an invalid number status. canceling FTP transfer.")
        
            failsafe(name=peer, mode="write")
            _un_hijack()
            #self.ui.update(force=True, new_data={'status': f'Pleasure doing FTP with you, {peer}.', 'face': '🍺(♥‿♥)'})
        #pass

    # called when a known peer is lost
    def on_peer_lost(self, agent, peer):
        #shutdown FTP server here
        self.ui.update(force=True, new_data={'status': f'We lost {peer} to The Reds!'})
        pass



