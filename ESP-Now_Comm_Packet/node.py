from common_esp import *
import time

espnow_setup()

print(format_mac(get_local_mac())) #My Board: 00:4B:12:BE:B9:C0
espnow_add_peer(b'\x34\xB4\x72\x70\x26\x74') # Host MAC
host_mac = b'\x34\xB4\x72\x70\x26\x74'

pending_time = 0

def on_receive(mac, msg, rssi):
    if msg:
        data = parse_msg_packet(msg)

        if data:
            now = time.ticks_ms()
            sent_time = data["timestamp"]

            latency = time.ticks_diff(now, sent_time)

            print(f"Latency: {latency} ms | RSSI: {rssi}")

espnow_set_recv_callback(on_receive)


packet = create_msg_packet(
    dest=host_mac,
    send=get_local_mac(),
    message="Hello from node",
    health={"bat":95},
    act=0x02    # sensor report
)

print("Packet Size: ", len(packet)) # need to see packet size

while True:
    espnow_send(host_mac, packet)
    print("Sent!")
    time.sleep(5)


