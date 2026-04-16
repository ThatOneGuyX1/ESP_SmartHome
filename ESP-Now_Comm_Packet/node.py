from common_esp import *
import time

espnow_setup()
espnow_set_recv_callback()

print("NODE MAC:", format_mac(get_local_mac()))

host_mac = b'\x34\xB4\x72\x70\x26\x74'
espnow_add_peer(host_mac)

while True:
    packet = create_msg_packet(
        dest=host_mac,
        send=get_local_mac(),
        message="ping",
        health={"bat": 95},
        act=0x02
    )

    espnow_send(host_mac, packet)
    print("Ping sent")

    time.sleep(3)