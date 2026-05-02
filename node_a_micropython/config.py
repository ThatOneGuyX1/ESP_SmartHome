"""
Node A Configuration — Constants, MACs, GPIO pins, thresholds.
Mirrors common.h / Kconfig from the C firmware.
"""
import time

# Node identification
NODE_TYPE_SENSOR_A = 0x01
NODE_TYPE_SENSOR_B = 0x02
NODE_TYPE_SENSOR_C = 0x03
NODE_TYPE_GATEWAY  = 0x00

# ESP-NOW configuration
ESPNOW_CHANNEL      = 1
MESH_DEFAULT_TTL     = 5
MESH_MAX_RETRIES     = 3
MESH_RETRY_DELAY_MS  = 100

# MAC addresses (update GATEWAY_MAC for your deployment)
BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
GATEWAY_MAC   = b'\xc0\xcd\xd6\x35\xc9\x98'

# Frame protocol sizes
MESH_HEADER_SIZE    = 22
MESH_MAX_FRAME_SIZE = 250
MESH_MAX_PAYLOAD    = MESH_MAX_FRAME_SIZE - MESH_HEADER_SIZE - 1  # 227

# I2C configuration (Feather V2)
I2C_SDA_PIN  = 22
I2C_SCL_PIN  = 20
I2C_FREQ     = 100_000

# PIR sensor
PIR_GPIO_PIN = 25

# Sensor task timing
SENSOR_SAMPLE_INTERVAL_MS = 30_000
HEALTH_REPORT_INTERVAL_MS = 120_000

# Temperature thresholds (C x 100)
TEMP_HIGH_THRESHOLD = 3500   # 35.00 C
TEMP_LOW_THRESHOLD  = 500    #  5.00 C

# Air quality thresholds (raw values 0-65535)
VOC_THRESHOLD = 35000
NOX_THRESHOLD = 18000

# Mode selection
NODE_ALWAYS_ON = True   # False = deep-sleep mode

# Deadband / adaptive reporting
TEMP_DEADBAND     = 50    # 0.50 C
HUMIDITY_DEADBAND = 200   # 2.00 %RH
LIGHT_DEADBAND    = 20    # 20 lux
MAX_SILENT_CYCLES = 6

# Moving average filter window
FILTER_WINDOW_SIZE = 5

# PIR debounce
VACANT_TIMEOUT_COUNT = 12


def mac_to_str(mac):
    """Format MAC bytes as XX:XX:XX:XX:XX:XX string."""
    return ':'.join('%02X' % b for b in mac)


def get_uptime_ms():
    """Return uptime in milliseconds (wraps to uint32)."""
    return time.ticks_ms() & 0xFFFFFFFF
