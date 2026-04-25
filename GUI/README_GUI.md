# Gui for ESP Smart Home
A modern, fully interactive Terminal User Interface (TUI) for monitoring,
filtering, and logging live serial data from a connected host device.

Built with [Textual](https://textual.textualize.io/) and [PySerial](https://pyserial.readthedocs.io/).

---

## Project Structure

```
GUI/
├── GUI.py              # Entry point — Textual TUI application
├── esp32+to_PC.py     # Serial reader backend (threaded PySerial)
├── config.py            # Default settings (port, baud, sensors, logging)
├── logger.py            # CSV data logger with hot-swap destination
├── requirements.txt     # Python dependencies
├── logs/                # Auto-created log output directory
│   └── serial_log.csv   # Default log file (CSV format)
└── README.md            # This file
```

---

## Features

| Feature | Description |
|---|---|
| **Live Data Display** | Real-time scrolling DataTable updated every 50 ms via async queue |
| **Sensor Selection** | Checkbox grid to enable/disable individual sensors — filters display & log |
| **Settings Panel** | Editable serial port, baud rate, and log destination — no restart needed |
| **Inline Log Viewer** | Last 500 log entries displayed inside the TUI on the Log tab |
| **CSV Logger** | Auto-creates timestamped CSV logs, hot-swappable directory & filename |
| **Pause / Resume** | Freeze the live view while data keeps accumulating in the queue |
| **Port Scanner** | Lists all available COM/tty ports and auto-fills the first detected |
| **Status Bar** | Live connection state, message count, and active log path |
| **Keyboard Shortcuts** | Full keybinding support for fast navigation and control |

---

## Layout

```
+---------------------------------------------------------------------+
|  Serial TUI                                          12:34:56        |
+------------+--------------+----------------+------------------------+
| Live Data  |   Sensors    |   Settings     |         Log            |
+------------+--------------+----------------+------------------------+
| [Connect] [Disconnect] [Clear]                                       |
| ------------------------------------------------------------------- |
|  Time         | Sensor       | Value          | Raw                  |
| --------------+--------------+----------------+------------------- |
|  12:34:56.123 | Temperature  | 25.3           | Temperature:25.3     |
|  12:34:56.174 | Humidity     | 61.2           | Humidity:61.2        |
|  12:34:56.225 | Voltage      | 3.31           | Voltage:3.31         |
|  12:34:56.276 | RPM          | 1450           | RPM:1450             |
|                                                                      |
+----------------------------------------------------------------------+
| CONNECTED  |  Messages: 142  |  Log: ./logs/serial_log.csv           |
+----------------------------------------------------------------------+
| ^C Quit   ^L Clear   ^P Pause/Resume   ^R Reconnect                 |
+---------------------------------------------------------------------+
```

---

## Prerequisites

- Python **3.10+** (required for Textual and modern type hints)
- A serial device connected via USB/UART (`/dev/ttyUSB0`, `COM3`, etc.)

---

## Installation and Setup

### 1. Clone or download the project

```bash
git clone https://github.com/yourname/serial-tui.git
cd serial-tui
```

### 2. (Recommended) Create a virtual environment

```bash
python -m venv .venv

# Activate — Linux / macOS
source .venv/bin/activate

# Activate — Windows
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python main.py
```

---

## Configuration (config.py)

All defaults live in `config.py`. Edit this file to match your device before launching.

```python
# Serial connection defaults
DEFAULT_PORT     = "/dev/ttyUSB0"   # Windows users: "COM3"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT  = 1                # seconds

# Sensor names your device broadcasts
AVAILABLE_SENSORS = [
    "Temperature",
    "Humidity",
    "Pressure",
    "Voltage",
    "Current",
    "RPM",
]

# Logging defaults
DEFAULT_LOG_DIR      = "./logs"
DEFAULT_LOG_FILENAME = "serial_log.csv"
LOG_ENABLED          = True

# Expected line format: "SensorName:Value\n"
DATA_DELIMITER = ":"
```

> These can also be changed live inside the Settings tab without editing the file.

---

## Expected Serial Data Format

Your device should send newline-terminated strings in the following format:

```
SensorName:Value\n
```

### Examples

```
Temperature:25.3
Humidity:61.2
Voltage:3.31
RPM:1450
Pressure:1013.25
```

> Any line that does not match `Name:Value` is captured as a `RAW` entry and
> still displayed and logged.

---

## File Descriptions

### main.py

The Textual TUI application and entry point. Defines all UI widgets, layout
(tabs, table, forms), event handlers, button callbacks, keybindings, the async
serial queue drain loop, and the status bar.

### serial_import.py

The serial backend. Manages opening/closing the port, runs a background
thread to read and parse incoming lines, and feeds structured data dictionaries
into a thread-safe `queue.Queue`. Fully decoupled from the UI.

### config.py

Central configuration for all defaults: port, baud rate, timeout, available
sensor names, log directory, log filename, log enabled state, and data
delimiter. Import this in any module that needs shared constants.

### logger.py

The CSV data logger. Opens and appends to a `.csv` file, supports runtime
hot-swapping of both the log directory and filename, and can be toggled on/off
without restarting. Columns: `timestamp`, `sensor`, `value`, `raw`.

### requirements.txt

Python package dependencies:

```
textual>=0.52.0
pyserial>=3.5
rich>=13.0.0
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `1` | Switch to Live Data tab |
| `2` | Switch to Sensors tab |
| `3` | Switch to Settings tab |
| `4` | Switch to Log tab |
| `Ctrl + L` | Clear live data table and reset message count |
| `Ctrl + P` | Pause / Resume live display (data still queued) |
| `Ctrl + R` | Reconnect to serial port using current settings |
| `Ctrl + C` | Quit the application cleanly |

---

## Sensor Selection Tab

The Sensors tab provides a checkbox grid for every sensor defined in
`AVAILABLE_SENSORS` (from `config.py`).

- **Checked** — data from that sensor is displayed in the live table and written to the log
- **Unchecked** — data from that sensor is silently discarded
- Press **Apply Sensor Filters** to commit your selection

> Sensors not listed in `AVAILABLE_SENSORS` but received as RAW lines are
> always passed through.

---

## Log File Format

Logs are written in CSV format to `./logs/serial_log.csv` by default.

```csv
timestamp,sensor,value,raw
12:34:56.123,Temperature,25.3,Temperature:25.3
12:34:56.174,Humidity,61.2,Humidity:61.2
12:34:56.225,Voltage,3.31,Voltage:3.31
```

### Changing the log destination at runtime

1. Go to the Settings tab
2. Update **Log Directory** and/or **Log Filename**
3. Press **Save Settings**

The current log file is closed and a new one is opened immediately — no data
loss and no restart required.

---

## Troubleshooting

### Serial port not found

```
Failed: [Errno 2] No such file or directory: '/dev/ttyUSB0'
```

- Go to the Settings tab and press **Scan Ports** to auto-detect available ports.
- Or run from the terminal:

```bash
python -m serial.tools.list_ports -v
```

### Permission denied on Linux / macOS

```bash
sudo usermod -aG dialout $USER
# Then log out and back in
```

### No data appearing in the table

- Verify the **baud rate** matches your device exactly.
- Check that your device is sending lines ending with `\n`.
- Confirm the **sensor names** in your data match entries in `AVAILABLE_SENSORS`
  or that the correct sensors are checked in the Sensors tab.
- Try the **Scan Ports** button to confirm the correct port is selected.

### Textual not displaying correctly

- Ensure your terminal supports **256-color** or **true-color** mode.
- Recommended terminals: iTerm2, Windows Terminal, GNOME Terminal, Alacritty, Kitty.
- Minimum terminal size: **80 x 24** characters.

---

## Extending the Application

### Add a new sensor

Open `config.py` and append to `AVAILABLE_SENSORS`:

```python
AVAILABLE_SENSORS = [
    ...
    "CO2_Level",   # new sensor
]
```

It will automatically appear in the Sensors tab checkbox grid.

### Change the data format

If your device uses a different delimiter (e.g. `=` or `,`), update:

```python
DATA_DELIMITER = "="   # in config.py
```

For more complex formats (JSON, binary), modify `_parse_line()` in `serial_import.py`.

### Add a new tab

In `main.py`, inside the `compose()` method, add a new `TabPane` block:

```python
with TabPane("Charts", id="charts"):
    with Vertical(classes="panel"):
        yield Label("Chart view coming soon...")
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| [textual](https://github.com/Textualize/textual) | `>=0.52.0` | TUI framework (widgets, layout, async) |
| [pyserial](https://github.com/pyserial/pyserial) | `>=3.5` | Serial port communication |
| [rich](https://github.com/Textualize/rich) | `>=13.0.0` | Terminal formatting (used by Textual) |

---

## License

MIT License — free to use, modify, and distribute.

---

## Acknowledgements

- [Textual by Textualize](https://textual.textualize.io/) — modern Python TUI framework
- [PySerial](https://pyserial.readthedocs.io/) — reliable Python serial communication library
- [Rich](https://rich.readthedocs.io/) — beautiful terminal output rendering

---

*Generated: April 06, 2026*
~~~