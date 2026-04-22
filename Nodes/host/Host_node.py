import smart_esp_comm as sh
import time

sh.boot()

LIGHT_1_MAC = sh.mac_bytes(sh.PEER_DICT["light_1"]["mac"])

while True:
    test_pkt = bytes([sh.ACT_TEST]) + bytes(66)  # 67 bytes total
    sh.espnow_send(LIGHT_1_MAC, test_pkt)
    print("[TEST] Ping sent to light_1")
    time.sleep(2)
    sh.poll_serial()
