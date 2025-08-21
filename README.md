## Main
In order to run, please run the following commands
```bash
sudo apt update
sudo apt install hostapd dnsmasq
sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo pip install pyftpdlib --break-system-packages
```
also, run this command:
```bash
sudo mkdir /etc/hostapd
sudo nano /etc/hostapd/hostapd.conf
```

And paste the following contents inside:

```bash
interface=wlan0
driver=nl80211
ssid=Dealbreaker
hw_mode=g
channel=6
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=PTWwohrnled
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

## Current Error(s)
* FTP Server Hosting / Wi-Fi Hotspot: the logs are reporting the server and Wi-Fi to be running, however cannot be found via. Network Interface
* FTP connection: Has not been tested

## Other, Non-important issues:
* Cannot find a way to update UI when called in a non-ui related function (ex. on_peer_detected)

# If a way to fix these is found, please create a pull request!
