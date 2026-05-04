# config.py
# Hardware and timing settings for motion_1 node.
# Node identity stays in config.json.

# ESP32 common I2C pins
# Change these if your board uses different pins.
I2C_SDA_PIN = 22
I2C_SCL_PIN = 20
I2C_FREQ = 100000

# I2C addresses
MPU6050_ADDR = 0x68
MAX17048_ADDR = 0x36

# LED setting
RED_LED_PIN = 13
RED_LED_ACTIVE_HIGH = True


# Reporting interval
REPORT_INTERVAL_MS = 2000

# Motion detection thresholds in m/s^2
# These match your earlier threshold style: X=3, Y=3, Z=7
THRESHOLD_X = 3.0
THRESHOLD_Y = 3.0
THRESHOLD_Z = 7.0

# Alert after this many motion hits
#HIT_LIMIT = 2

# Calibration
CALIBRATION_SAMPLES = 50
CALIBRATION_DELAY_MS = 20

# Battery settings
LOW_BATTERY_PERCENT = 20

# Debug
PRINT_I2C_SCAN = True
PRINT_TX_DEBUG = True
PRINT_MOTION_DEBUG = True