from common_esp import *
import time

# =========================
# SETUP
# =========================
espnow_setup()
espnow_set_recv_callback()

print("NODE MAC:", format_mac(get_local_mac()))

host_mac = b'\x34\xB4\x72\x70\x26\x74'
espnow_add_peer(host_mac)

# =========================
# LED STATUS
# =========================
IS_STRONGEST = False
last_host_heard = time.ticks_ms()

# Default state:
# Red = connected
set_led(255, 0, 0)

# =========================
# MAIN LOOP
# =========================
while True:

    # -------------------------
    # SEND PING TO HOST
    # -------------------------
    packet = create_msg_packet(
        dest=host_mac,
        send=get_local_mac(),
        message="ping",
        health={"bat": 95},
        act=0x02
    )

    espnow_send(host_mac, packet)
    print("Ping sent")

    # -------------------------
    # CHECK FOR INCOMING PACKETS
    # -------------------------
    pkt = get_next_packet()

    if pkt:
        mac, msg = pkt[:2]

        if msg:
            data = parse_msg_packet(msg)

            if data:
                # Record last host communication
                last_host_heard = time.ticks_ms()

                # -------------------------
                # HOST SAYS THIS NODE
                # IS THE STRONGEST
                # -------------------------
                if data["action"] == 0xD1:

                    if data["destination"] == get_local_mac():
                        IS_STRONGEST = True
                        # GREEN
                        set_led(0, 255, 0)
                        print("[STATUS] I am strongest node")

                    else:
                        IS_STRONGEST = False
                        # RED
                        set_led(255, 0, 0)

    # -------------------------
    # CONNECTION TIMEOUT
    # -------------------------
    age = time.ticks_diff(
        time.ticks_ms(),
        last_host_heard
    )

    # If host silent >15 sec
    if age > 15000:

        # OFF = disconnected
        set_led(0, 0, 0)

    time.sleep(3)