"""
Air Quality Node — SGP41 VOC + NOX Sensor
ECE 568 Smart Home Mesh Network (MicroPython)
"""
import machine
import uasyncio as asyncio

import smart_esp_comm as sh
from sensor_hal import SensorHAL
from max17048 import MAX17048
import sensor_task
import health_task

import time

print('========================================')
print('  Air Quality Node -- VOC / NOX (SGP41)')
print('  ECE 568 Smart Home Mesh Network')
print('  (MicroPython)')
print('========================================')

# Boot ESP-NOW, load identity + peer map, register receive IRQ
sh.boot()

# Shared I2C bus
i2c = machine.I2C(
    0,
    sda=machine.Pin(8),
    scl=machine.Pin(9),
    freq=100_000,
)

hal        = SensorHAL(i2c=i2c)
fuel_gauge = MAX17048(i2c)

# ── One-shot health report on boot ────────────────────────────────────
fuel_gauge.init()
health_task.health_send_once(sh, fuel_gauge)

# ── Mode selection ────────────────────────────────────────────────────
ALWAYS_ON = True


i = 0
HOST_MAC = sh.mac_bytes(sh.PEER_DICT["host"]["mac"])
while i < 5:
        pkt = sh.create_msg_packet(
            dest_mac = HOST_MAC,
            action   = sh.ACT_TEST,
            message  = b'',
        )
        sh.espnow_send(HOST_MAC, pkt)
        print(f"[TEST] Ping #{i} sent")
        time.sleep(2)
        i+=1

if ALWAYS_ON:
    async def main():
        await asyncio.gather(
            sensor_task.sensor_loop(hal, sh),
            health_task.health_loop(sh, fuel_gauge),
        )

    asyncio.run(main())

else:
    sensor_task.deep_sleep_one_shot(hal, sh)
