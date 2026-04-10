from common_esp import *

espnow_setup()

print(format_mac(get_local_mac())) # My Board: 34:B4:72:70:26:74
espnow_add_peer(b'\x00\x4B\x12\xBE\xB9\xC0') # Node MAC

NETWORK_MAP = {}

def on_receive(mac, msg, rssi):
    if msg:
        data = parse_msg_packet(msg)

        if data:
            print("\n[RECEIVED PACKET]")
            print("From: ", data["sender"])
            print("RSSI: ", rssi)
            print("Battery: ", data["battery"])
            print("Message: ", data["message"])

            reply_packet = create_msg_packet(
                dest=bytes.fromhex(data["sender"].replace(':','')),
                send=get_local_mac(),
                message="back",
                health={"bat": 100},
                act=0x03
            )

            print("Reply size: ", len(reply_packet)) # debug
            espnow_send(bytes.fromhex(data["sender"].replace(':','')), reply_packet)

            # update network map
            sender = data["sender"]

            NETWORK_MAP[sender] = {
                "last_seen": time.ticks_ms(),
                "battery": data["battery"],
                "rssi": rssi
        }

        print("\n[NETWORK MAP]")
        for node, info in NETWORK_MAP.items():
            age = time.ticks_diff(time.ticks_ms(), info["last_seen"])

            print(f"{node} | RSSI: {info['rssi']} | Battery: {info['battery']} | Last Seen: {age} ms ago")


espnow_set_recv_callback(on_receive)
