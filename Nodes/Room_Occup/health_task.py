"""
Health Task — periodic device diagnostics reporting.
ECE 568 Smart Home Mesh Network (MicroPython + smart_esp_comm)

Sends a health report packet toward home (ACT_REPORT_HOME) containing:
  - Battery voltage (mV) and SoC (%) from MAX17048
  - Heap free (bytes) and uptime (ms)
  - Chip temp stubbed to 0 (not available on ESP32 original)

The 32-byte message payload is packed as:
  Bytes 0-1 : battery_mv  (uint16, little-endian)
  Byte  2   : battery_soc (uint8,  0-100)
  Byte  3   : chip_temp   (int8,   °C, stubbed 0)
  Bytes 4-7 : heap_free   (uint32, little-endian)
  Bytes 8-11: uptime_ms   (uint32, little-endian)
  Bytes 12-31: reserved / zero-padded
"""
import gc
import struct
import time
import uasyncio as asyncio

import config
import smart_esp_comm as comm

# Health message payload format (12 bytes used of 32 available)
_HEALTH_FMT = '<HBbII'   # battery_mv, soc, chip_temp, heap_free, uptime_ms


def _build_health_payload(fuel_gauge) -> bytes:
    """Collect diagnostics and pack into a 12-byte struct."""
    battery_mv  = fuel_gauge.read_voltage_mv()
    battery_soc = fuel_gauge.read_soc()
    chip_temp   = 0          # not available on ESP32 original
    gc.collect()
    heap_free  = gc.mem_free()
    uptime_ms  = time.ticks_ms() & 0xFFFFFFFF

    print('[HEALTH] battery=%u mV  soc=%u%%  heap=%u B  uptime=%u ms' % (
        battery_mv, battery_soc, heap_free, uptime_ms))

    return struct.pack(_HEALTH_FMT,
                       battery_mv, battery_soc, chip_temp,
                       heap_free, uptime_ms)


def health_send_once(fuel_gauge):
    """
    Collect a single health snapshot and send it toward home.

    Uses ACT_REPORT_HOME so relay nodes will forward it hop by hop.
    Health data is embedded in the packet's message field (not the
    dedicated health block) so it survives multi-hop forwarding intact.
    """
    payload = _build_health_payload(fuel_gauge)

    # Find the home node MAC from the peer map
    next_hop = comm._find_next_hop_toward_home()
    if next_hop is None:
        # We are home (LOCAL_HOP == 0) or no route -- print locally
        print('[HEALTH] At home node or no route -- health logged locally.')
        return

    pkt = comm.create_msg_packet(
        dest_mac = next_hop,
        action   = comm.ACT_REPORT_HOME,
        message  = payload,
    )
    comm.espnow_send(next_hop, pkt)
    print('[HEALTH] Health report sent toward home.')


async def health_loop(fuel_gauge, interval_ms=None):
    """
    Async health reporting loop for always-on mode.

    Args:
        fuel_gauge : initialized MAX17048 instance
        interval_ms: override for HEALTH_REPORT_INTERVAL_MS
    """
    if interval_ms is None:
        interval_ms = config.HEALTH_REPORT_INTERVAL_MS

    fuel_gauge.init()
    print('[HEALTH] Health task running (interval=%d ms)' % interval_ms)

    while True:
        health_send_once(fuel_gauge)
        await asyncio.sleep_ms(interval_ms)
