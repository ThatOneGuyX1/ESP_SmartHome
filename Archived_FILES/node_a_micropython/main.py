"""
Node A — Occupancy/Temp/Light Sensor
ECE 568 Smart Home Mesh Network (MicroPython)
"""
import machine
import time
import struct

import Archived_FILES.node_a_micropython.config as config
import Archived_FILES.node_a_micropython.message as message
from Archived_FILES.node_a_micropython.mesh_comm import MeshComm
from Archived_FILES.node_a_micropython.sensor_hal import SensorHAL
from Archived_FILES.node_a_micropython.max17048 import MAX17048
import Archived_FILES.node_a_micropython.sensor_task as sensor_task
import Archived_FILES.node_a_micropython.health_task as health_task

print('========================================')
print('  Node A -- Occupancy/Temp/Light Sensor')
print('  ECE 568 Smart Home Mesh Network')
print('  (MicroPython)')
print('========================================')

# Shared I2C bus
i2c = machine.I2C(
    0,
    sda=machine.Pin(config.I2C_SDA_PIN),
    scl=machine.Pin(config.I2C_SCL_PIN),
    freq=config.I2C_FREQ
)

# Hardware objects
hal = SensorHAL(i2c=i2c)
fuel_gauge = MAX17048(i2c)
mesh = MeshComm()
mesh.init()


# ── Command handler ────────────────────────────────────────────────────
def command_handler(frame):
    """Process incoming COMMAND frames from the gateway."""
    if frame['msg_type'] != message.MSG_TYPE_COMMAND:
        return
    if frame['payload_len'] < 1:
        return

    cmd_id, data = message.unpack_command(frame['payload'])

    if cmd_id == message.CMD_SET_TEMP_THRESHOLDS:
        if frame['payload_len'] >= 5:
            high = struct.unpack_from('<h', data, 0)[0]
            low = struct.unpack_from('<h', data, 2)[0]
            print('[NODE_A] CMD: Set temp thresholds high=%.2f C low=%.2f C' % (
                high / 100, low / 100))
            sensor_task.set_temp_thresholds(high, low)

    elif cmd_id == message.CMD_SET_SAMPLE_INTERVAL:
        if frame['payload_len'] >= 5:
            interval = struct.unpack_from('<I', data, 0)[0]
            print('[NODE_A] CMD: Set sample interval to %u ms' % interval)
            sensor_task.sample_interval_ms = interval

    elif cmd_id == message.CMD_REQUEST_READING:
        print('[NODE_A] CMD: Immediate reading requested')

    else:
        print('[NODE_A] CMD: Unknown command_id=0x%02X' % cmd_id)


mesh.register_recv_cb(command_handler)

# ── Discovery beacon ──────────────────────────────────────────────────
disc_payload = message.pack_discovery(
    config.NODE_TYPE_SENSOR_A,
    0xFF,   # distance_level unknown
    0x0F    # capabilities: temp + humidity + light + PIR
)
ok = mesh.send(config.BROADCAST_MAC, message.MSG_TYPE_DISCOVERY, disc_payload)
if ok:
    print('[NODE_A] Discovery beacon broadcast')

# ── One-shot health report ────────────────────────────────────────────
fuel_gauge.init()
health_task.health_send_once(mesh, fuel_gauge)


# ── Mode selection ────────────────────────────────────────────────────
if config.NODE_ALWAYS_ON:
    # Always-on relay mode: run async event loop
    import uasyncio as asyncio

    async def main():
        await asyncio.gather(
            mesh.recv_loop(),
            sensor_task.sensor_loop(hal, mesh),
            health_task.health_loop(mesh, fuel_gauge),
        )

    asyncio.run(main())

else:
    # Deep-sleep mode: single read/send, then sleep
    sensor_task.deep_sleep_one_shot(hal, mesh)
    # Never reaches here
