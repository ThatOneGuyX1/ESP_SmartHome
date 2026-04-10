from common_esp import *

espnow_setup()

print(format_mac(get_local_mac())) # My Board: 34:B4:72:70:26:74

espnow_add_peer(b'\x00\x4B\x12\xBE\xB9\xC0') # Node MAC

def on_receive(mac, msg):
    if msg:
        data = parse_msg_packet(msg)

        if data:
            print("\n[RECEIVED PACKET]")
            print("From: ", data["sender"])
            print("Action: ", data["action"])
            print("Battery: ", data["battery"])
            print("Message: ", data["message"])
        else:
            print("[RAW]", msg)


espnow_set_recv_callback(on_receive)
