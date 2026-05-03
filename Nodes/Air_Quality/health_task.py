"""
Health Task — periodic device diagnostics reporting.
Uses smart_esp_comm for all ESP-NOW communication.
"""
import gc
import time

HEALTH_REPORT_INTERVAL_MS = 120_000


def health_send_once(comm, fuel_gauge):
    """Collect and send a single health report via ACT_REPORT_HOME."""
    battery_mv  = fuel_gauge.read_voltage_mv()
    battery_soc = fuel_gauge.read_soc()
    gc.collect()
    heap_free  = gc.mem_free()
    uptime_ms  = time.ticks_ms() & 0xFFFFFFFF

    print('[HEALTH] battery=%u mV (%u%%)  heap=%u B  uptime=%u ms' % (
        battery_mv, battery_soc, heap_free, uptime_ms))

    gateway_mac = _next_hop(comm)
    if gateway_mac is None:
        print('[HEALTH] No route to home -- health report not sent.')
        return

    pkt = comm.create_msg_packet(
        dest_mac = gateway_mac,
        action   = comm.ACT_REPORT_HOME,
        message  = b'',
        health   = {
            "temp":    0,           # no temperature sensor on this node
            "battery": battery_soc,
            "uptime":  uptime_ms // 1000,
        },
    )
    comm.espnow_send(gateway_mac, pkt)


async def health_loop(comm, fuel_gauge, interval_ms=None):
    """Async health reporting loop for always-on mode."""
    import uasyncio as asyncio

    if interval_ms is None:
        interval_ms = HEALTH_REPORT_INTERVAL_MS

    print('[HEALTH] Health task running (interval=%d ms)' % interval_ms)
    while True:
        health_send_once(comm, fuel_gauge)
        await asyncio.sleep_ms(interval_ms)


def _next_hop(comm):
    """Return MAC bytes of best neighbor toward home, or None."""
    best_name = None
    best_hop  = comm.LOCAL_HOP
    for name in comm._get_my_neighbors():
        if name not in comm.PEER_DICT:
            continue
        peer_hop = comm.PEER_DICT[name]["hop"]
        if peer_hop < best_hop:
            best_hop  = peer_hop
            best_name = name
    if best_name is None:
        return None
    return comm.mac_bytes(comm.PEER_DICT[best_name]["mac"])