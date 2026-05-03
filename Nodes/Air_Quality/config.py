"""
Air Quality Node Configuration — Constants, MACs, GPIO pins, thresholds.
"""
import time

# Node identification
NODE_TYPE_AIR_QUALITY = 0x04
NODE_TYPE_GATEWAY     = 0x00

# ESP-NOW configuration
ESPNOW_CHANNEL      = 1
MESH_DEFAULT_TTL    = 5
MESH_MAX_RETRIES    = 3
MESH_RETRY_DELAY_MS = 100

# MAC addresses (update GATEWAY_MAC for your deployment)
BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
GATEWAY_MAC   = b'\xc0\xcd\xd6\x35\xc9\x98'

# Frame protocol sizes
MESH_HEADER_SIZE    = 22
MESH_MAX_FRAME_SIZE = 250
MESH_MAX_PAYLOAD    = MESH_MAX_FRAME_SIZE - MESH_HEADER_SIZE - 1  # 227

# I2C configuration (Feather V2)
I2C_SDA_PIN = 22
I2C_SCL_PIN = 20
I2C_FREQ    = 100_000

# Sensor task timing
SENSOR_SAMPLE_INTERVAL_MS = 5_000
HEALTH_REPORT_INTERVAL_MS = 120_000

# Air quality thresholds (raw SGP41 values, 0–65535)
VOC_THRESHOLD = 35000
NOX_THRESHOLD = 18000

# Mode selection
NODE_ALWAYS_ON = True   # False = deep-sleep mode

# Adaptive reporting
VOC_DEADBAND      = 500
NOX_DEADBAND      = 500
MAX_SILENT_CYCLES = 6

# Moving average filter window
FILTER_WINDOW_SIZE = 5


def mac_to_str(mac):
    """Format MAC bytes as XX:XX:XX:XX:XX:XX string."""
    return ':'.join('%02X' % b for b in mac)


def get_uptime_ms():
    """Return uptime in milliseconds (wraps to uint32)."""
    return time.ticks_ms() & 0xFFFFFFFF