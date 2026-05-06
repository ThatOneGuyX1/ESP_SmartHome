# ESP SmartHome — PC GUI

A modern, fully interactive Terminal User Interface (TUI) for monitoring,
filtering, and logging live mesh telemetry from the Host ESP over USB serial.

Built with [Textual](https://textual.textualize.io/) and
[PySerial](https://pyserial.readthedocs.io/).

---

## Where this fits in the system

```
 ┌────────────────────────┐                 ┌────────────────────────┐
 │   air_quality   hop 1  │                 │   leak_sensor   hop 1  │
 │   ─────────────────    │                 │   ─────────────────    │
 │  • SHT41  temp, RH     │                 │  • ADC moisture probe  │
 │  • BH1750 light (lux)  │                 │  → "LEAK:<adc>"        │
 │  • SGP41  VOC, NOx     │                 │  • MAX17048 battery    │
 │  → "T:..C H:..% L:..lux" │                │                        │
 │  • MAX17048 battery    │                 │                        │
 └───────────┬────────────┘                 └───────────┬────────────┘
             │                                          │
 ┌───────────┴────────────┐                 ┌───────────┴────────────┐
 │   room_occup    hop 1  │                 │  Raspberry Pi  + cam   │
 │   ─────────────────    │                 │   ─────────────────    │
 │  • PIR motion sensor   │                 │  • MobileNet SSD AI    │
 │  → "PIR:0/1"           │                 │    person detection    │
 │  • SHT41 temp, RH      │                 │  → UDP {event:person}  │
 │  • MAX17048 battery    │                 └───────────┬────────────┘
 └───────────┬────────────┘                             │  UDP/WiFi (5005)
             │                                          ▼
             │                              ┌────────────────────────┐
             │                              │  Camera Bridge  hop 1  │
             │                              │   ─────────────────    │
             │                              │  • UDP → mesh adapter  │
             │                              │  → "CAM:PERSON:<conf>" │
             │                              │  → "CAM:CLEAR"         │
             │                              └───────────┬────────────┘
             │                                          │
             └──────────────┬───────────────────────────┘
                            │  ESP-NOW mesh
                            │  67-byte packets
                            │  action = ACT_REPORT_HOME
                            │  + optional 10-byte health block
                            │  + 10-byte hop trail
                            ▼
                  ┌──────────────────────┐
                  │   Host ESP   hop 0   │
                  │   ───────────────    │
                  │  • Receives packets  │
                  │  • Decodes header,   │
                  │    payload, health,  │
                  │    trail             │
                  │  • Emits JSON lines  │
                  │    over UART         │
                  │  • Accepts ASCII     │
                  │    commands back     │
                  └──────────┬───────────┘
                             │  USB serial  (115200 8N1)
                             │
                             │  ▲ JSON lines:                     ▼ ASCII commands:
                             │  {"type":"sensor_report",          LIST  / SYNC
                             │   "sender":"...",                  ADD <name> <mac> ...
                             │   "message":"...",                 REMOVE <name>
                             │   "trail":[...],                   SETNAME / SETHOP / SETID
                             │   "health":{...}}
                             ▼
                  ┌──────────────────────┐
                  │     PC + GUI         │
                  │     (this app)       │
                  │                      │
                  │  📊 Dashboard cards  │
                  │  📡 Live Log table   │
                  │  🚨 Alerts panel     │
                  │  🔬 Sensor filter    │
                  │  ⚙️  Settings + Cmds │
                  │  📋 Raw Log          │
                  │                      │
                  │  ↘ CSV + JSONL       │
                  │     on disk          │
                  └──────────────────────┘
```

The four sensor sources reach the host through the same mesh, so the GUI
treats them uniformly — each shows up as a `sensor_report` JSON line and
gets its own dashboard card. The only difference between them is the
shape of the `message` string (`T:..`, `LEAK:`, `PIR:`, `CAM:`), which
the dashboard parses with sensor-specific regex.

**Data path (sensor → screen):**
1. A sensor node samples its hardware and builds a 32-byte payload (e.g. `LEAK:3100`, `T:22.5C H:48% PIR:1`).
2. It wraps the payload in a 67-byte ESP-NOW packet with action byte `ACT_REPORT_HOME` and forwards it toward the host. Each forwarding node appends its 1-byte ID to the hop trail.
3. The Host ESP (`LOCAL_HOP == 0`) receives the packet, decodes it, and prints **one JSON object per line** over USB serial via `handle_report_home()`.
4. The GUI's `SerialReader` reads lines, drops anything not starting with `{`, parses the JSON, stamps a local timestamp, and pushes onto an async queue.
5. The async drain loop pulls each packet, updates the matching dashboard card, adds rows to the live log + alerts table, and writes both `.csv` and `.jsonl` to disk.

**Command path (GUI → mesh):** the GUI's Mesh Commands panel writes ASCII
commands (`LIST`, `SYNC`, `ADD …`, etc.) back over the same serial link.
The Host ESP's `handle_serial_command()` parses them and acts on the mesh
(updates the local peer map, propagates sync packets, etc.).

The camera flow is slightly different: the Raspberry Pi sends UDP/JSON
person-detection events to the **Camera Bridge ESP32**, which converts
them into mesh `CAM:PERSON:<conf>` / `CAM:CLEAR` packets. From the GUI's
point of view those look identical to any other `sensor_report`.

---

## Project Structure

```
GUI/
├── GUI.py              # Textual TUI app — entry point
├── config.py           # Defaults: port, baud, sensors, thresholds, log paths
├── logger.py           # CSV + parallel JSONL logger with hot-swap destination
├── requirements.txt    # Python dependencies
├── logs/               # Auto-created; one pair per session
│   ├── smarthome_log_<YYYY-MM-DD_HH-MM>.csv     # Flat columns
│   └── smarthome_log_<YYYY-MM-DD_HH-MM>.jsonl   # Full structured packets (replay-friendly)
└── README_GUI.md       # This file
```

---

## Features

| Feature | Description |
|---|---|
| **Live Dashboard** | One card per node with live values, sparkline trends (temp + humidity), battery, uptime, **hop count + trail**, last-seen, and a stale indicator |
| **Live Log** | Color-coded scrolling DataTable updated every 50 ms via async queue |
| **Alerts Panel** | Filtered alert history (leak detected, person events, explicit `alert` types) with a count in the status bar |
| **Sensor Filter** | Per-sensor checkboxes — disable a sensor and its packets are silently dropped from display + log |
| **Settings Panel** | Editable port, baud, log directory, log filename, logging on/off — applied without restart |
| **Mesh Command Panel** | Send raw commands to the Host ESP (or use quick **LIST** / **SYNC** buttons) |
| **CSV + JSONL Logging** | Every packet appended to both formats. Each program launch gets its own timestamped pair so sessions don't bleed together. CSV is human-readable; JSONL preserves full structure for replay |
| **Replay Mode** | Load any prior CSV or JSONL log and stream it through the same pipeline — perfect for demos without hardware |
| **Demo Mode** | `--demo` flag injects synthetic packets so the UI works with no device attached |
| **Pause / Resume** | Freeze the live view while data keeps queuing |
| **Port Scanner** | Lists all available COM/tty ports and auto-fills the first detected |
| **Status Bar** | Live connection state, message count, alert count, and active log path |
| **Stale Detection** | Cards turn red and gain a `⚠ STALE` badge if a node hasn't reported in `STALE_THRESHOLD` seconds (default 15) |
| **Audible Alert Bell** | Terminal bell rings whenever a new alert lands |
| **Keyboard Shortcuts** | Tab-switch + clear/pause/reconnect/quit |

---

## Layout

```
+─────────────────────────────────────────────────────────────────────+
| ESP SmartHome TUI                                       12:34:56    |
+──────────────+───────────+─────────+──────────+──────────+──────────+
| 📊 Dashboard | 📡 Live   | 🚨 Alerts | 🔬 Sensors | ⚙️  Settings | 📋 Log |
+──────────────+───────────+─────────+──────────+──────────+──────────+
| [Connect] [Disconnect]   PAUSED                                     |
| ─────────────────────────────────────────────────────────────────── |
| Live Node Status — cards appear as nodes check in                   |
|                                                                     |
| ┌─ leak_sensor  ● LIVE ──────────────┐ ┌─ room_occup  ● LIVE ─────┐ |
| │ UNKNOWN                            │ │ UNKNOWN                  │ |
| │ ──────────────────────             │ │ ──────────────────────   │ |
| │ Temp:      —                       │ │ Temp:      22.5°C  ▂▃▅▆█ │ |
| │ Humidity:  —                       │ │ Humidity:  48%     ▆▅▆▆▆ │ |
| │ Light:     —                       │ │ Light:     — lux         │ |
| │ Motion:    —                       │ │ Motion:    OCCUPIED      │ |
| │ Leak:      DETECTED (ADC:3100)     │ │ Leak:      —             │ |
| │ Camera:    —                       │ │ Camera:    —             │ |
| │ ──────────────────────             │ │ ──────────────────────   │ |
| │ Battery: 87%   Uptime: 3600s       │ │ Battery: 86%   Uptime: … │ |
| │ Hops: 3   Trail: 11 → 5 → 1        │ │ Hops: 1   Trail: 2       │ |
| │ Last seen: 12:34:56                │ │ Last seen: 12:34:58      │ |
| │ ⚠  LEAK DETECTED (ADC:3100)        │ │                          │ |
| └────────────────────────────────────┘ └──────────────────────────┘ |
+─────────────────────────────────────────────────────────────────────+
| ● CONNECTED  │  Messages: 142  │  🚨 1 alert  │  Log: ./logs/...    |
+─────────────────────────────────────────────────────────────────────+
| ^C Quit  ^L Clear  ^P Pause  ^R Reconnect   1-6 switch tabs         |
+─────────────────────────────────────────────────────────────────────+
```

---

## Prerequisites

- Python **3.10+** (Textual requires 3.10+ syntax)
- A Host ESP32 connected via USB and emitting `ACT_REPORT_HOME` JSON lines
- A terminal with 256-color or true-color support and at least 80×24

---

## Installation and Setup

### 1. Create a virtual environment (recommended)

```bash
cd GUI
python -m venv .venv

# Activate — Linux / macOS
source .venv/bin/activate

# Activate — Windows
.venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Edit defaults if needed

Open `config.py` and adjust `DEFAULT_PORT`, `DEFAULT_BAUDRATE`, sensor list,
log paths, etc. (Or leave them and override at runtime via the Settings tab.)

### 4. Run the application

```bash
python GUI.py             # live mode
python GUI.py --demo      # injected fake packets, no hardware needed
python GUI.py --replay logs/smarthome_log.jsonl   # replay a prior session
```

---

## Configuration (`config.py`)

```python
DEFAULT_PORT     = "COM7"
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT  = 1

AVAILABLE_SENSORS = ["temperature", "humidity", "motion", "pressure", "leak", "camera"]

DEFAULT_LOG_DIR      = "<GUI>/logs"
DEFAULT_LOG_FILENAME = "smarthome_log.csv"
LOG_ENABLED          = True

STALE_THRESHOLD = 15      # seconds before a card goes stale
MAX_HISTORY     = 14      # sparkline points kept per node
SPARK_CHARS     = "▁▂▃▄▅▆▇█"
LEAK_THRESHOLD  = 1000    # ADC value above which LEAK packets become alerts

ROW_COLORS = {
    "sensor_data":   "white",
    "sensor_report": "white",
    "health":        "cyan",
    "alert":         "bold red",
    "discovery":     "green",
}
```

> Most of these can be changed live in the Settings tab without restarting.

---

## Expected Serial Data Format

The Host ESP emits one JSON object per line:

```json
{"type":"sensor_report","sender":"leak_sensor","message":"LEAK:3100","trail":[11,5,1],"health":{"temp":24,"battery":87,"uptime":3600},"timestamp":null}
```

| Field | Notes |
|---|---|
| `type` | Currently always `sensor_report` from the Host ESP. The GUI also recognizes `sensor_data`, `health`, `alert`, `discovery` (used by demo packets and reserved for future expansion). |
| `sender` | Peer name from the host's peer list (e.g. `leak_sensor`, `air_quality`, `room_occup`). |
| `message` | Sensor-specific text the GUI parses with regex. Recognized prefixes: |
| | • `T:..C H:..% L:..lux PIR:0/1` — environmental + occupancy |
| | • `LEAK:<adc>` — water leak ADC reading |
| | • `CAM:PERSON:<conf>` / `CAM:CLEAR` — camera person detection |
| `trail` | Hop trail (list of node IDs along the path home). Rendered on the card. |
| `health` | Optional `{temp, battery, uptime}`. |
| `timestamp` | The GUI overwrites this with the local clock on receipt. |

Lines that don't start with `{` are silently dropped (so the host's
`[BOOT]`, `[ROUTE]`, `[RX]` debug prints don't pollute the UI).

---

## Tabs

| # | Tab | Purpose |
|---|---|---|
| 1 | 📊 Dashboard | One card per node — live values, sparklines, battery, uptime, hop trail, last-seen, stale flag |
| 2 | 📡 Live Log | Color-coded scrolling table of every parsed packet |
| 3 | 🚨 Alerts | Filtered view — leak detections, explicit `alert` types. Counted in status bar. |
| 4 | 🔬 Sensors | Per-sensor checkboxes — currently filters `LEAK:` and `CAM:` packets |
| 5 | ⚙️  Settings | Connection settings, log destination, **mesh command panel** |
| 6 | 📋 Log | Raw text view of the last 500 entries |

---

## Sensor Selection

The Sensors tab provides a checkbox grid for every sensor in `AVAILABLE_SENSORS`.

- **Checked** — packets from that sensor are displayed and logged
- **Unchecked** — packets are silently discarded by the live pipeline (still readable from the file logs)
- Press **Apply Filters** to commit your selection

Currently the filter recognizes `LEAK:` and `CAM:` message prefixes. Other
sensor data (temperature, humidity, motion, pressure) flows through
regardless.

---

## Mesh Commands (Settings tab)

The host's `smart_esp_comm.py` parses these commands from USB serial:

| Command | Purpose |
|---|---|
| `LIST` | Print all known peers, hop, ID, neighbor flag |
| `SYNC` | Manually push the peer map outward through the mesh |
| `ADD <name> <mac> <hop> <id> <neighbor1,neighbor2,…>` | Add a peer (auto-propagates) |
| `REMOVE <name>` | Remove a peer (auto-propagates) |
| `SETNAME <name>` / `SETHOP <hop>` / `SETID <id>` | Provision this node's identity |

The Settings tab now exposes:

- A free-form text Input + **Send** button
- Quick buttons for **LIST** and **SYNC**

Sending requires an active connection. The status line shows ✔ / ✖.

> The `ADD` / `REMOVE` / `SETNAME` / `SETHOP` / `SETID` commands change
> network state. Use deliberately.

---

## Logging

Every parsed packet is appended to two files in parallel:

### `smarthome_log.csv`
```csv
timestamp,type,sender,message,temp,battery,uptime
12:34:56,sensor_report,leak_sensor,LEAK:3100,,87,3600
12:34:58,sensor_report,room_occup,T:22.5C H:48% PIR:1,24,86,3660
```

### `smarthome_log.jsonl`
```jsonl
{"type":"sensor_report","sender":"leak_sensor","message":"LEAK:3100","trail":[11,5,1],"health":{"temp":24,"battery":87,"uptime":3600},"timestamp":"12:34:56"}
{"type":"sensor_report","sender":"room_occup","message":"T:22.5C H:48% PIR:1","trail":[2],"health":{"temp":24,"battery":86,"uptime":3660},"timestamp":"12:34:58"}
```

The JSONL file preserves trail and full structure, so it round-trips
perfectly through replay mode.

### Changing the log destination at runtime

1. Go to the Settings tab
2. Update **Log Directory** and/or **Log Filename**
3. Press **Save Settings**

The current files are closed and new ones opened immediately — no data
loss, no restart. Both `.csv` and `.jsonl` follow the new path.

---

## Replay Mode

Stream a prior log through the GUI as if it were live:

```bash
python GUI.py --replay logs/smarthome_log.jsonl   # preferred — full structure
python GUI.py --replay logs/smarthome_log.csv     # also supported
```

Packets play at ~0.4s spacing. Dashboard cards, alerts, live log, and the
raw log all populate as if the data were arriving over serial. Useful for:

- Demos when no hardware is attached
- Debugging UI behavior against a captured incident
- Comparing display logic across two log files

JSONL replay preserves hop trail and exact message structure. CSV replay
reconstructs as much as possible from the flat columns (trail is empty
since CSV doesn't carry it).

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `1` | Switch to Dashboard tab |
| `2` | Switch to Live Log tab |
| `3` | Switch to Alerts tab |
| `4` | Switch to Sensors tab |
| `5` | Switch to Settings tab |
| `6` | Switch to Log tab |
| `Ctrl + L` | Clear the live data table and reset message count |
| `Ctrl + P` | Pause / resume the live display (data keeps queuing) |
| `Ctrl + R` | Disconnect and reconnect using current settings |
| `Ctrl + C` | Quit the application cleanly |

---

## File Descriptions

### `GUI.py`
The Textual TUI application and entry point. Defines all UI widgets,
layout (tabs, dashboard cards, tables, forms), event handlers, button
callbacks, keybindings, the async serial queue drain loop, the status
bar, and the demo / replay packet injectors. Also implements the
outbound command panel that writes to the open serial port.

### `config.py`
Central configuration for all defaults: port, baud rate, timeout,
sensor names, log directory + filename, log enabled state, stale
threshold, sparkline parameters, leak threshold, and message-type row
colors. Imported by both `GUI.py` and `logger.py` so there is a single
source of truth.

### `logger.py`
The packet logger. Opens and appends to a `.csv` file *and* a parallel
`.jsonl` file (same base name). Supports runtime hot-swapping of both
the directory and filename, and can be toggled on/off without restarting.
- CSV columns: `timestamp, type, sender, message, temp, battery, uptime`
- JSONL: full packet structure including `trail`

### `requirements.txt`

```
textual>=0.52.0
pyserial>=3.5
rich>=13.0.0
```

---

## Troubleshooting

### Serial port not found

```
Failed: [Errno 2] No such file or directory: '/dev/ttyUSB0'
```

- Settings tab → **Scan Ports** to auto-detect available ports.
- Or run from the terminal:

```bash
python -m serial.tools.list_ports -v
```

### Permission denied on Linux / macOS

```bash
sudo usermod -aG dialout $USER     # log out and back in
```

### No data appearing

- Verify the **baud rate** matches the Host ESP (`115200`).
- The Host ESP must be the gateway (`LOCAL_HOP == 0`) and have peers reporting.
- Lines from the host must start with `{` — boot/route prints are dropped.
- Confirm the correct port is selected (Settings → Scan Ports).
- If a sensor's data is missing, check the Sensors tab — its checkbox might be off.

### Card appears but values stay "—"

The GUI extracts values via regex on the `message` field. If the sensor
node uses a different format, either:
- Update the regex in `NodeCard.absorb()` in `GUI.py`, or
- Ask the firmware author to emit a recognized prefix.

### Textual not displaying correctly

- Ensure your terminal supports **256-color** or **true-color**.
- Recommended: Windows Terminal, iTerm2, GNOME Terminal, Alacritty, Kitty.
- Minimum size: **80 × 24**.

### Mesh command says "Not connected"

The send path uses the live serial connection. Connect first (Dashboard
or Live Log tab → Connect button), then go to Settings → Mesh Commands.

---

## Extending the Application

### Add a new sensor

1. Append to `AVAILABLE_SENSORS` in `config.py`:

   ```python
   AVAILABLE_SENSORS = [
       ...
       "co2",
   ]
   ```

   It will automatically appear in the Sensors tab checkbox grid.

2. If the sensor uses a new message prefix (e.g. `CO2:412`), add a regex
   branch in `NodeCard.absorb()` and a new state field for it.

### Add a recognized message format

Edit `NodeCard.absorb()` in `GUI.py`. The current parser supports:

```python
T:25.3C H:48% L:120lux PIR:1
LEAK:3100
CAM:PERSON:87
CAM:CLEAR
```

Add a new branch with `re.search(...)` matching your format.

### Add a new tab

Inside `compose()` in `GUI.py`, add a `TabPane` block:

```python
with TabPane("Charts", id="charts"):
    with Vertical(classes="panel"):
        yield Label("Chart view coming soon...")
```

Then add a `Binding("7", "show_tab('charts')")` next to the others.

### Add a new column to the CSV log

Edit `DataLogger.FIELDNAMES` in `logger.py` and update `DataLogger.log()`
to write the new field. JSONL needs no changes — it always carries the
full packet.

---

## Dependencies

| Package | Purpose |
|---|---|
| [textual](https://github.com/Textualize/textual) | TUI framework (widgets, layout, async) |
| [pyserial](https://github.com/pyserial/pyserial) | Serial port communication |
| [rich](https://github.com/Textualize/rich) | Terminal formatting (transitive via Textual) |

---

## Known Limitations

- **No outbound command logging.** Commands you send via the Mesh Commands
  panel are echoed in the status line but not written to the CSV/JSONL log.
- **CSV replay drops trail.** The trail is preserved in JSONL but not CSV
  columns — replay from JSONL if you want hops/trail to show up.
- **Air quality VOC/CO2** are not yet extracted by the dashboard regex.
- **Camera image stream** is not surfaced — the GUI only sees
  `CAM:PERSON:<conf>` / `CAM:CLEAR` events through the mesh.

---

## Acknowledgements

- [Textual by Textualize](https://textual.textualize.io/) — modern Python TUI framework
- [PySerial](https://pyserial.readthedocs.io/) — reliable Python serial communication
- [Rich](https://rich.readthedocs.io/) — terminal output rendering
