In order to run, please run the following commands
```sudo apt update```
```sudo apt install hostapd dnsmasq```
```sudo systemctl unmask hostapd```
```sudo systemctl enable hostapd```
```sudo pip install pyftpdlib --break-system-packages```
also, run this command:
```sudo mkdir /etc/hostapd/```
```sudo nano /etc/hostapd/hostapd.conf```

And paste the following contents inside:

```interface=wlan0
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
rsn_pairwise=CCMP```
