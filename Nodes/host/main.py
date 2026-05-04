import smart_esp_comm as sh

sh.espnow_setup()

# Force channel to match WiFi AP (camera_bridge uses AP channel, not ch6)
import network
_sta = network.WLAN(network.STA_IF)
_sta.config(channel=11)
print("[HOST] Channel:", _sta.config('channel'))
sh.load_config()
sh.load_peers()

e = sh.get_espnow()
for entry in sh.PEER_DICT.values():
    try:
        e.add_peer(sh.mac_bytes(entry["mac"]))
    except OSError:
        pass

print("[HOST] Listening...")
while True:
    mac, raw = e.irecv(5000)  # block up to 5s waiting for a packet
    if mac and raw:
        print("[RX] From", sh.format_mac(mac), "len", len(raw))
        if len(raw) == sh.PKT_TOTAL_SIZE:
            pkt = sh.parse_packet(raw)
            sh.handle_report_home(pkt)
        else:
            print("[RX] raw[0]=", hex(raw[0]))
    sh.poll_serial()
