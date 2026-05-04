from machine import Pin
import neopixel
import network
import espnow
import time
import json
import urandom

# =========================
# LED SETUP
# =========================

neo_power = Pin(20, Pin.OUT)
neo_power.value(1)
np = neopixel.NeoPixel(Pin(9), 1)
CURRENT_LED = None

def set_led(r, g, b):
    np[0] = (r, g, b)
    np.write()

def _set_state(color):
    global CURRENT_LED
    if CURRENT_LED != color:
        CURRENT_LED = color
        set_led(*color)

def led_booting():  _set_state((0, 0, 255))    # blue
def led_direct():   _set_state((0, 255, 0))    # green
def led_relay():    _set_state((0, 255, 255))  # cyan
def led_forward():  _set_state((180, 0, 255))  # purple
def led_search():   _set_state((255, 255, 0))  # yellow

# =========================
# GLOBALS
# Update HOST_MAC to match your host board's MAC address.
# Run on host REPL to get it:
#   import network; w=network.WLAN(0); w.active(True); print(bytes(w.config('mac')))
# =========================

HOST_MAC      = b'\x58\xE6\xC5\xF5\x79\xF8'
BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'

# Packet action types
ACT_PING  = 1   # heartbeat/routing packet — carries sender temp
ACT_ROUTE = 2   # Node B beacon — carries Node B temp

esp_instance = None
local_mac    = None
_recv_pending = False
recv_queue   = []
SEEN         = {}

# =========================
# UTIL
# =========================

def format_mac(mac):
    if mac is None:
        return "NONE"
    if isinstance(mac, str):
        return mac
    return ':'.join('{:02X}'.format(b) for b in mac)

def new_pid():
    return urandom.getrandbits(16)

# =========================
# ESP-NOW SETUP
# Broadcast-only architecture — no unicast peers needed except
# BROADCAST_MAC itself.  This eliminates all peer table and
# channel-mismatch issues that plagued the unicast approach.
# =========================

def espnow_setup():
    global esp_instance, local_mac

    sta = network.WLAN(network.WLAN.IF_STA)
    sta.active(True)
    sta.disconnect()
    sta.config(channel=6)
    local_mac = sta.config('mac')

    e = espnow.ESPNow()
    e.active(True)
    e.config(rxbuf=2048)          # generous buffer — broadcast traffic is higher
    e.add_peer(BROADCAST_MAC, channel=6)

    esp_instance = e
    print("[ESP] local MAC:", format_mac(local_mac))

def espnow_reinit():
    """
    Full ESP-NOW stack reset — cycles active(False)/active(True) to
    flush stale radio state on the C6 after sustained relay operation.
    Broadcast sends silently fail after relay period without this reset.
    """
    global esp_instance
    e = esp_instance
    try:
        e.irq(None)
        e.active(False)
    except:
        pass
    time.sleep_ms(100)
    try:
        e.active(True)
        e.config(rxbuf=2048)
        e.add_peer(BROADCAST_MAC, channel=6)
        espnow_set_recv_callback()
        print("[ESP] reinit complete")
    except Exception as ex:
        print("[ESP] reinit failed:", ex)

def get_espnow():   return esp_instance
def get_local_mac(): return local_mac

def espnow_send_bcast(msg):
    """Send to BROADCAST_MAC. All boards on ch6 receive it."""
    e = get_espnow()
    if isinstance(msg, str):
        msg = msg.encode()
    try:
        e.send(BROADCAST_MAC, msg, False)  # False = non-blocking
        return True
    except Exception as ex:
        print("[SEND FAIL]", ex)
        return False

# =========================
# RECEIVE — IRQ sets flag, main loop drains
# =========================

def espnow_set_recv_callback():
    e = get_espnow()
    def cb(_):
        global _recv_pending
        _recv_pending = True
    e.irq(cb)

def drain_recv_queue():
    global _recv_pending
    if not _recv_pending:
        return
    _recv_pending = False
    e = get_espnow()
    while True:
        pkt = e.irecv(0)
        if pkt is None or pkt[0] is None:
            break
        recv_queue.append(pkt)

def get_next_packet():
    if recv_queue:
        return recv_queue.pop(0)
    return None

# =========================
# PACKETS
# =========================

def parse_packet(msg):
    try:
        if isinstance(msg, (bytes, bytearray)):
            msg = msg.decode()
        return json.loads(msg)
    except:
        return None

def packet_seen(sender, pid):
    """Return True if we've already processed this sender+pid combo."""
    key = "{}-{}".format(sender, pid)
    if key in SEEN:
        return True
    SEEN[key] = time.ticks_ms()
    return False

def cleanup_seen():
    """Remove dedup entries older than 15 seconds."""
    now = time.ticks_ms()
    dead = [k for k, ts in SEEN.items()
            if time.ticks_diff(now, ts) > 15000]
    for k in dead:
        del SEEN[k]