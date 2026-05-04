from common_esp import *
import esp32
import time

espnow_setup()   # must be called BEFORE reading local_mac

NODE_B_MAC_STR = '58:E6:C5:F6:79:E0'
HOST_MAC_STR   = format_mac(HOST_MAC)
LOCAL_MAC_STR  = format_mac(get_local_mac())   # safe — called after setup

espnow_set_recv_callback()

print("NODE A:", LOCAL_MAC_STR)
led_booting()

# =========================
# STATE
# =========================

last_ping       = 0
PING_INTERVAL   = 2000

last_relay_seen = 0
RELAY_DEAD_MS   = 9000

using_relay     = False

def read_temp():
    try:
        return esp32.mcu_temperature()
    except:
        return 0

# =========================
# PROCESS INCOMING PACKET
# =========================

def process_packet(mac, msg):
    global last_relay_seen, using_relay

    data = parse_packet(msg)
    if not data:
        return

    sender = data.get("sender", "")
    pid    = data.get("pid", 0)

    if sender == LOCAL_MAC_STR:
        return

    if packet_seen(sender, pid):
        return

    if data.get("action") == ACT_ROUTE and sender == NODE_B_MAC_STR:
        last_relay_seen = time.ticks_ms()
        using_relay     = True
        print("[NODE A] relay alive")

# =========================
# SEND PING
# =========================

def send_ping():
    temp = read_temp()
    pkt = {
        "sender": LOCAL_MAC_STR,
        "action": ACT_PING,
        "path":   [LOCAL_MAC_STR],
        "ttl":    3,
        "pid":    new_pid(),
        "data":   {"temp": temp, "node": "A"},
    }
    espnow_send_bcast(json.dumps(pkt))
    print("[NODE A] ping  temp={:.1f}C  relay={}".format(temp, using_relay))

# =========================
# MAIN LOOP
# =========================

while True:
    now = time.ticks_ms()

    drain_recv_queue()
    pkt = get_next_packet()
    if pkt:
        mac, msg = pkt[:2]
        if msg:
            process_packet(mac, msg)

    if using_relay and last_relay_seen > 0:
        if time.ticks_diff(now, last_relay_seen) > RELAY_DEAD_MS:
            using_relay = False
            print("[NODE A] relay dead — reinitialising radio")
            espnow_reinit()   # reset C6 radio state for clean direct sends

    led_relay() if using_relay else led_direct()

    if time.ticks_diff(now, last_ping) > PING_INTERVAL:
        send_ping()
        last_ping = now

    cleanup_seen()
    time.sleep_ms(50)