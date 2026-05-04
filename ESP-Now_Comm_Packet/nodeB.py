from common_esp import *
import esp32
import time

espnow_setup()

HOST_MAC_STR  = format_mac(HOST_MAC)
LOCAL_MAC_STR = format_mac(get_local_mac())

espnow_set_recv_callback()

print("NODE B:", LOCAL_MAC_STR)
led_booting()

last_beacon     = 0
BEACON_INTERVAL = 3000
last_forward    = 0
FORWARD_FLASH   = 200
cached_temp     = 0   # updated each beacon cycle, used in forwards

def read_temp():
    try:
        return esp32.mcu_temperature()
    except:
        return 0

# =========================
# FORWARD NODE A's PING
# Appends Node B to path and adds cached temp as relay_data.
# Uses cached_temp to avoid expensive sensor read inside forward.
# =========================

def forward_packet(data):
    global last_forward

    if data.get("ttl", 0) <= 1:
        return

    path = data.get("path", [])
    if LOCAL_MAC_STR in path:
        return

    fwd = {
        "sender":     data["sender"],
        "action":     ACT_PING,
        "path":       path + [LOCAL_MAC_STR],
        "ttl":        data["ttl"] - 1,
        "pid":        data["pid"],
        "data":       data.get("data", {}),
        "relay_temp": cached_temp,
    }

    espnow_send_bcast(json.dumps(fwd))
    last_forward = time.ticks_ms()
    print("[NODE B] fwd path={}".format(len(fwd["path"])))

# =========================
# PROCESS INCOMING PACKET
# =========================

def process_packet(mac, msg):
    data = parse_packet(msg)
    if not data:
        return

    sender = data.get("sender", "")
    pid    = data.get("pid", 0)

    if sender == LOCAL_MAC_STR:
        return

    if packet_seen(sender, pid):
        return

    if data.get("action") == ACT_PING:
        forward_packet(data)

# =========================
# BEACON
# =========================

def send_beacon():
    global cached_temp
    cached_temp = read_temp()
    pkt = {
        "sender": LOCAL_MAC_STR,
        "action": ACT_ROUTE,
        "path":   [],
        "ttl":    1,
        "pid":    new_pid(),
        "data":   {"temp": cached_temp, "node": "B"},
    }
    espnow_send_bcast(json.dumps(pkt))
    print("[NODE B] beacon  temp={:.1f}C".format(cached_temp))

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

    if time.ticks_diff(now, last_forward) < FORWARD_FLASH:
        led_forward()
    else:
        led_direct()

    if time.ticks_diff(now, last_beacon) > BEACON_INTERVAL:
        send_beacon()
        last_beacon = now

    cleanup_seen()
    time.sleep_ms(50)