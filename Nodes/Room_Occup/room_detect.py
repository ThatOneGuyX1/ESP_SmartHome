import smart_esp_comm as sh
import time

sh.boot()

LIGHT_1_MAC = sh.mac_bytes(sh.PEER_DICT["light_1"]["mac"])


test_pkt = sh.create_msg_packet(
    dest_mac = LIGHT_1_MAC,
    action   = sh.ACT_TEST,
    message  = b''
)
sh.espnow_send(LIGHT_1_MAC, test_pkt)
print("[TEST] Ping sent to light_1")
time.sleep(2)
sh.poll_serial()

cycle = 0

while cycle < 5:

    test_pkt = sh.create_msg_packet(
    dest_mac = LIGHT_1_MAC,
    action   = sh.ACT_REQ_ACTION,
    message  = b''
)
    sh.espnow_send(LIGHT_1_MAC, test_pkt)
    print("[Action Request] Ping sent to light_1")
    time.sleep(2)
    sh.poll_serial()
    cycle += 1



