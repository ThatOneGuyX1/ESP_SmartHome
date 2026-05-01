# config.py
# -----------------------------------------------------------
# Central configuration for the Serial TUI application.
# Modify defaults here or override them via the Settings panel.
# -----------------------------------------------------------

# --- Serial Port Defaults ---
DEFAULT_PORT     = "/dev/ttyUSB0"   # Windows: "COM3"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT  = 1                # seconds

# --- Available Sensors ---
# Add or remove sensor names that your device broadcasts
AVAILABLE_SENSORS = [
    "Temperature",
    "Humidity",
    "Pressure",
    "Voltage",
    "Current",
    "RPM",
]

# --- Logging Defaults ---
DEFAULT_LOG_DIR      = "./logs"
DEFAULT_LOG_FILENAME = "serial_log.csv"
LOG_ENABLED          = True

# --- Data Format ---
# Expected line format from device: "SensorName:Value\n"
# Example: "Temperature:25.3"
DATA_DELIMITER = ":"