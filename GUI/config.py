import os

DEFAULT_PORT     = "COM7"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT  = 1

AVAILABLE_SENSORS = ["temperature", "humidity", "motion", "pressure", "leak", "camera"]

DEFAULT_LOG_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
DEFAULT_LOG_FILENAME = "smarthome_log.csv"
LOG_ENABLED          = True

STALE_THRESHOLD = 15
MAX_HISTORY     = 14
SPARK_CHARS     = "▁▂▃▄▅▆▇█"
LEAK_THRESHOLD  = 1000

ROW_COLORS = {
    "sensor_data":   "white",
    "sensor_report": "white",
    "health":        "cyan",
    "alert":         "bold red",
    "discovery":     "green",
}
