import smart_esp_comm as sh
import time

sh.boot()

"""
"""

e = sh.get_espnow()
print("[DEBUG] Registered ESP-NOW peers:")
for p in e.get_peers():
    print("  ", ':'.join('%02X' % b for b in p[0]))
    
    
import network
sta = network.WLAN(network.WLAN.IF_STA)
print("[DIAG] Host channel: %d" % sta.config('channel'))

'''
'''

LIGHT_1_MAC = sh.mac_bytes(sh.PEER_DICT["light_1"]["mac"])

LEAK_MAC = sh.mac_bytes(sh.PEER_DICT["leak_sensor"]["mac"])

# Initial test ping
test_pkt = sh.create_msg_packet(
    dest_mac = LIGHT_1_MAC,
    action   = sh.ACT_TEST,
    message  = b''
)
sh.espnow_send(LIGHT_1_MAC, test_pkt)
print("[TEST] Ping sent to light_1")
time.sleep(2)

# Uncomment to send 5 action requests to light_1
# for _ in range(5):
#     pkt = sh.create_msg_packet(
#         dest_mac = LIGHT_1_MAC,
#         action   = sh.ACT_REQ_ACTION,
#         message  = b''
#     )
#     sh.espnow_send(LIGHT_1_MAC, pkt)
#     print("[ACTION] Request sent to light_1")
#     time.sleep(2)

print("[HOST] Listening... (serial commands: ADD, REMOVE, LIST, SYNC)")
cycle = 0
while True:
    cycle = cycle+1
    sh.poll_serial()
    if cycle % 25 == 0:
        print("Still Tunning")
        cycle = 0
        
        test_pkt = sh.create_msg_packet(
            dest_mac = LEAK_MAC,
            action   = sh.ACT_TEST,
            message  = b'1010100110101'
        )
        sh.espnow_send(LEAK_MAC, test_pkt)
        print("[TEST] Ping sent to LEAK_MAC")
        time.sleep(2)
    time.sleep(0.1)
    flag = sh.check_request_flag()
    if flag:
        print("message recived")
        
        
        
