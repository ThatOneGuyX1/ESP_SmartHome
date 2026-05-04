from common_esp import *
import time

espnow_setup()
espnow_set_recv_callback()

print("HOST:", format_mac(get_local_mac()))

HOST_MAC_STR = format_mac(HOST_MAC)

# =========================
# STATE
# =========================

# NETWORK: mac_str -> {parent, last_seen, link}
NETWORK = {}

# NODE_STATS: mac_str -> {ping, route, direct, relayed}
NODE_STATS = {}

# SENSOR_DATA: mac_str -> {temp, node, hops, last_seen}
SENSOR_DATA = {}

NODE_TIMEOUT = 15000   # expire node after 15s of silence

def _bump(mac, field):
    if mac not in NODE_STATS:
        NODE_STATS[mac] = {"ping":0,"route":0,"direct":0,"relayed":0}
    NODE_STATS[mac][field] = NODE_STATS[mac].get(field, 0) + 1

def _store_sensor(mac, data_field, hops, now):
    if data_field and "temp" in data_field:
        SENSOR_DATA[mac] = {
            "temp":     data_field["temp"],
            "node":     data_field.get("node", "?"),
            "hops":     hops,
            "last_seen": now,
        }

# =========================
# PROCESS PACKET
# =========================

def process_packet(mac, msg):
    data = parse_packet(msg)
    if not data:
        return

    sender = data.get("sender", "")
    action = data.get("action")
    path   = data.get("path", [])
    now    = time.ticks_ms()

    # Drop our own broadcast echoes
    if sender == HOST_MAC_STR:
        return

    # NOTE: No packet_seen() on the host. The host processes every copy
    # of every packet. Node A's direct ping (path length 1) and Node B's
    # forwarded copy (path length 2) both arrive — processing both keeps
    # NETWORK[NodeB].last_seen fresh and shows the relay topology correctly.
    # Dedup is only needed on nodes to prevent forwarding loops.

    # ---- ACT_ROUTE: Node B beacon ----
    if action == ACT_ROUTE:
        _bump(sender, "route")
        NETWORK[sender] = {
            "parent":    "HOST",
            "last_seen": now,
            "link":      "announce",
        }
        _store_sensor(sender, data.get("data"), 1, now)
        return

    # ---- ACT_PING: heartbeat from any node ----
    if action != ACT_PING:
        return

    if not path:
        return

    originator = path[0]

    if len(path) == 1:
        # Direct ping — always re-parent to HOST regardless of prior state.
        # This handles the failover case where Node A was previously shown
        # as a child of Node B but is now pinging directly.
        _bump(originator, "ping")
        _bump(originator, "direct")
        NETWORK[originator] = {
            "parent":    "HOST",
            "last_seen": now,
            "link":      "direct",
        }
        _store_sensor(originator, data.get("data"), 1, now)

    else:
        # Relayed ping — Node A -> Node B -> Host
        relay = path[-1]
        child = path[0]
        _bump(relay, "ping")
        _bump(child, "ping")
        _bump(relay, "relayed")
        _bump(child, "relayed")
        NETWORK[relay] = {
            "parent":    "HOST",
            "last_seen": now,
            "link":      "relay",
        }
        NETWORK[child] = {
            "parent":    relay,
            "last_seen": now,
            "link":      "via-relay",
        }
        # Node A's temp from the data field
        _store_sensor(child, data.get("data"), 2, now)
        # Node B's temp piggybacks as relay_temp in every forwarded packet
        relay_temp = data.get("relay_temp")
        if relay_temp is not None:
            _store_sensor(relay,
                          {"temp": relay_temp, "node": "B"},
                          1, now)

# =========================
# EXPIRY WITH ORPHAN ADOPTION
# =========================

def short(mac):
    return mac[-5:] if mac and len(mac) >= 5 else mac

def _expire(mac_str, now):
    """Delete node, re-parent its children to HOST with fresh timestamp."""
    del NETWORK[mac_str]
    adopted = set()
    for n, info in NETWORK.items():
        if info["parent"] == mac_str:
            info["parent"]    = "HOST"
            info["last_seen"] = now
            adopted.add(n)
            print("[HOST] orphan adopted:", short(n))
    return adopted

# =========================
# DISPLAY
# =========================

def display():
    print("\033[2J\033[H", end="")
    print("=" * 60)
    print("   SELF-HEALING ESP-NOW MESH  —  BATMAN-style")
    print("=" * 60)
    print()

    now = time.ticks_ms()

    # Expire stale nodes — protect freshly adopted orphans
    dead = [n for n, info in NETWORK.items()
            if time.ticks_diff(now, info["last_seen"]) > NODE_TIMEOUT]
    protected = set()
    for n in dead:
        if n in NETWORK and n not in protected:
            protected |= _expire(n, now)

    # Topology tree
    direct = [n for n, info in NETWORK.items()
               if info["parent"] == "HOST"]

    if not direct:
        print("  [ HOST ]  — no nodes connected")
        print()
    else:
        print("  ┌─ [ HOST ]")
        for relay in sorted(direct):
            children = [n for n, info in NETWORK.items()
                        if info["parent"] == relay]
            info_r = NETWORK[relay]
            age_r  = time.ticks_diff(now, info_r["last_seen"]) // 1000
            link_r = info_r.get("link", "?")
            if children:
                print("  │")
                print("  ├── [ {} ]  (relay)  age={}s  link={}".format(
                    short(relay), age_r, link_r))
                for child in sorted(children):
                    info_c = NETWORK[child]
                    age_c  = time.ticks_diff(now, info_c["last_seen"]) // 1000
                    link_c = info_c.get("link", "?")
                    print("  │    └── [ {} ]  age={}s  link={}".format(
                        short(child), age_c, link_c))
            else:
                print("  │")
                print("  ├── [ {} ]  age={}s  link={}".format(
                    short(relay), age_r, link_r))
        print()

    # Sensor data
    print("-" * 60)
    print("  SENSOR DATA")
    print("-" * 60)
    shown = False
    for mac, s in sorted(SENSOR_DATA.items()):
        if mac not in NETWORK:
            continue
        shown = True
        age = time.ticks_diff(now, s["last_seen"]) // 1000
        hop_str = "direct" if s["hops"] <= 1 else "{}-hop".format(s["hops"])
        print("  [ {} ]  temp={:.1f}C  node={}  ({})  age={}s".format(
            short(mac), s["temp"], s["node"], hop_str, age))
    if not shown:
        print("  (no sensor data)")
    print()

    # Debug stats
    print("-" * 60)
    print("  DEBUG  node_timeout={}s".format(NODE_TIMEOUT // 1000))
    print("-" * 60)
    all_macs = set(NETWORK.keys()) | set(NODE_STATS.keys())
    if not all_macs:
        print("  (no stats yet)")
    for mac in sorted(all_macs):
        live   = mac in NETWORK
        status = "LIVE" if live else "GONE"
        age    = "{}s".format(
            time.ticks_diff(now, NETWORK[mac]["last_seen"]) // 1000
        ) if live else "---"
        s = NODE_STATS.get(mac, {})
        print("  [{}] {}  age={}  ping={} dir={} relay={} route={}".format(
            status, short(mac), age,
            s.get("ping",0), s.get("direct",0),
            s.get("relayed",0), s.get("route",0)))
    print("=" * 60)
    print()

# =========================
# MAIN LOOP
# =========================

last_display = 0

while True:
    drain_recv_queue()
    pkt = get_next_packet()
    if pkt:
        mac, msg = pkt[:2]
        if msg:
            process_packet(mac, msg)

    if time.ticks_diff(time.ticks_ms(), last_display) > 3000:
        display()
        last_display = time.ticks_ms()

    cleanup_seen()
    time.sleep_ms(50)