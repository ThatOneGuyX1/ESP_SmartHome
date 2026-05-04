"""
Health Task — periodic device diagnostics reporting.
Mirrors health_task.c from the C firmware.
"""
import gc
import time

import Archived_FILES.node_a_micropython.config as config
import Archived_FILES.node_a_micropython.message as message


def health_send_once(mesh, fuel_gauge):
    """Collect and send a single health report."""
    battery_mv = fuel_gauge.read_voltage_mv()
    battery_soc = fuel_gauge.read_soc()
    chip_temp = 0  # not available on ESP32 original
    rssi = mesh.get_last_rssi()
    gc.collect()
    heap_free = gc.mem_free()
    uptime_ms = config.get_uptime_ms()

    print('[HEALTH] Health: battery=%u mV (%u%%) heap=%u bytes uptime=%u ms rssi=%d dBm' % (
        battery_mv, battery_soc, heap_free, uptime_ms, rssi))

    payload = message.pack_health(
        battery_mv, battery_soc, chip_temp,
        rssi, heap_free, uptime_ms
    )
    return mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_HEALTH, payload)


async def health_loop(mesh, fuel_gauge, interval_ms=None):
    """Async health reporting loop for always-on mode."""
    import uasyncio as asyncio

    if interval_ms is None:
        interval_ms = config.HEALTH_REPORT_INTERVAL_MS

    fuel_gauge.init()
    print('[HEALTH] Health task running (interval=%d ms)' % interval_ms)

    while True:
        health_send_once(mesh, fuel_gauge)
        await asyncio.sleep_ms(interval_ms)
