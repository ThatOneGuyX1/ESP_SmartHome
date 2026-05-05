"""
Light Sensor Node Configuration

Hardware constants, GPIO pins, I2C addresses, timing, and reporting settings.

Node identity fields such as name, hop, and id should stay in config.json.
smart_esp_comm.py loads those values from config.json.
"""

# ─────────────────────────────────────────────
# I2C configuration
# ESP8266 setup from your working wiring:
# SDA = GPIO14
# SCL = GPIO12
# ─────────────────────────────────────────────
I2C_SDA_PIN = 4
I2C_SCL_PIN = 5
I2C_FREQ = 100000


HOST_MAC_STR = "00:4B:12:BE:BC:B4"  # replace with your actual host MAC
LOCAL_NAME = "light_1"
LOCAL_ID = 5
ESPNOW_CHANNEL = 6
# ─────────────────────────────────────────────
# I2C device addresses
# ─────────────────────────────────────────────
BH1750_ADDR = 0x23
MAX17048_ADDR = 0x36

# ─────────────────────────────────────────────
# Reporting timing
# ─────────────────────────────────────────────
LIGHT_REPORT_INTERVAL_MS = 5000      # Send light report every 5 seconds
HEALTH_REPORT_INTERVAL_MS = 30000    # Optional separate health interval later

# ─────────────────────────────────────────────
# Battery health settings
# ─────────────────────────────────────────────
LOW_BATTERY_PERCENT = 20             # Low battery warning threshold
BATTERY_TEMP_STUB_C = 0              # MAX17048 is not a temperature sensor

# ─────────────────────────────────────────────
# Message settings
# smart_esp_comm.py supports max 32-byte message payload.
# ─────────────────────────────────────────────
MAX_SENSOR_MSG_BYTES = 32

# ─────────────────────────────────────────────
# Debug controls
# ─────────────────────────────────────────────
PRINT_I2C_SCAN = True
PRINT_TX_DEBUG = True
#PRINT_MEMORY_DEBUG = True

# ─────────────────────────────────────────────
# Optional startup delay
# Helps sensors settle after boot.
# ─────────────────────────────────────────────
#BOOT_DELAY_MS = 500