"""
Node A — Occupancy / Temp / Light Sensor
ECE 568 Smart Home Mesh Network (MicroPython + smart_esp_comm)

Boot order:
  1. smart_esp_comm.boot()  — ESP-NOW up, identity loaded, peers loaded,
                              receive IRQ registered.
  2. I2C bus + hardware objects created.
  3. One-shot health report sent immediately.
  4. Async event loop launched: sensor_loop + health_loop run concurrently.

Incoming packets (commands from the gateway, relay traffic) are handled
inside smart_esp_comm.on_receive() via the IRQ.  main.py registers an
additional application-level hook (_app_recv_hook) that intercepts
ACT_REQ_ACTION packets so the main loop can respond to gateway commands.
"""
import machine
from machine import SoftI2C, Pin
import uasyncio as asyncio

import config
import smart_esp_comm as comm
from sensor_hal import SensorHAL
from max17048  import MAX17048
import sensor_task
import health_task

# ── Banner ────────────────────────────────────────────────────────────
print('========================================')
print('  Node A -- Occupancy/Temp/Light Sensor')
print('  ECE 568 Smart Home Mesh Network')
print('  (MicroPython + smart_esp_comm)')
print('========================================')

# ── 1. Boot ESP-NOW mesh layer ────────────────────────────────────────
#
# smart_esp_comm.boot() performs, in order:
#   espnow_setup()               → WLAN STA up, mac_local populated
#   load_config()                → LOCAL_NAME / LOCAL_HOP / LOCAL_ID from config.json
#   load_peers()                 → PEER_DICT from peer_file.json, neighbors registered
#   espnow_set_recv_callback()   → on_receive() armed as ESP-NOW IRQ
#
comm.boot()

# ── 2. Hardware objects ───────────────────────────────────────────────
#
# Single shared I2C bus for DHT20 (0x38) and BH1750 (0x23).
# MAX17048 fuel gauge also sits on this bus (0x36).
#
i2c = SoftI2C(Pin(8), Pin(9))

hal        = SensorHAL(i2c=i2c)
fuel_gauge = MAX17048(i2c)

# ── 3. Application-level receive hook (optional extension point) ───────
#
# smart_esp_comm.on_receive() already handles routing (ACT_REPORT_HOME,
# ACT_SYNC_PEERS) and sets REQUEST_FLAG for ACT_REQ_ACTION packets.
# If you need to act on REQUEST_FLAG in an async task, poll it here:
#
async def _command_poll_loop():
    """
    Poll the REQUEST_FLAG set by smart_esp_comm when an ACT_REQ_ACTION
    packet arrives.  Extend this to handle specific command payloads.
    """
    while True:
        if comm.check_request_flag():
            print('[NODE_A] ACT_REQ_ACTION flag set -- handling request.')
            # TODO: inspect the packet payload for specific commands
            # (set temp thresholds, change sample interval, force reading)
            # Reset flag after handling
            comm.REQUEST_FLAG = False
        await asyncio.sleep_ms(200)   # poll at 5 Hz, well below IRQ rate

# ── 4. Async main ─────────────────────────────────────────────────────

async def main():
    # One-shot health report at boot (before entering the loop)
    health_task.health_send_once(fuel_gauge)

    await asyncio.gather(
        sensor_task.sensor_loop(hal),
        health_task.health_loop(fuel_gauge),
        _command_poll_loop(),
    )

asyncio.run(main())
