"""
Node Configuration — Hardware constants, GPIO pins, thresholds, timing.
ECE 568 Smart Home Mesh Network (MicroPython + smart_esp_comm)

Node identity (name, hop, id) lives in config.json and is loaded
exclusively by smart_esp_comm.load_config(). Do not duplicate those
fields here.
"""

# ── I2C configuration (Adafruit Feather ESP32 V2) ─────────────────────
I2C_SDA_PIN = 22
I2C_SCL_PIN = 20
I2C_FREQ    = 100_000

# ── PIR sensor ────────────────────────────────────────────────────────
PIR_GPIO_PIN = 25

# ── Task timing ───────────────────────────────────────────────────────
SENSOR_SAMPLE_INTERVAL_MS  = 30_000   # 30 s between sensor reads
HEALTH_REPORT_INTERVAL_MS  = 120_000  # 2 min between health reports

# ── Temperature alert thresholds (°C × 100) ───────────────────────────
TEMP_HIGH_THRESHOLD = 3500   # 35.00 °C
TEMP_LOW_THRESHOLD  = 500    #  5.00 °C

# ── Adaptive reporting deadbands ──────────────────────────────────────
TEMP_DEADBAND     = 50    # 0.50 °C
HUMIDITY_DEADBAND = 200   # 2.00 %RH
LIGHT_DEADBAND    = 20    # 20 lux
MAX_SILENT_CYCLES = 6     # Force a send after this many skipped cycles

# ── Moving average filter ─────────────────────────────────────────────
FILTER_WINDOW_SIZE = 5

# ── PIR debounce ──────────────────────────────────────────────────────
VACANT_TIMEOUT_COUNT = 12  # Consecutive vacant reads before state changes

