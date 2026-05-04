# ESP SmartHome — PC GUI

Terminal dashboard for the ESP-NOW mesh smart-home system. Reads JSON-line
telemetry from the Host ESP over USB serial, surfaces live node status,
alerts, and a CSV log.

Built with [Textual](https://textual.textualize.io/) and
[PySerial](https://pyserial.readthedocs.io/).

---

## Where this fits in the system

```
[ Sensor Nodes ] --ESP-NOW--> [ Host ESP (hop 0) ] --USB serial--> [ PC GUI ]
                                                  JSON lines       (this app)
```

The Host ESP receives mesh packets (`ACT_REPORT_HOME`), decodes them, and
prints one JSON object per line over USB. The GUI parses those lines and
ignores everything else (boot prints, route logs, etc.).

---

## Files

```
GUI/
├── GUI.py            Textual TUI app — entry point
├── config.py         Defaults: port, baud, sensors, thresholds, log paths
├── logger.py         CSV logger with hot-swappable destination
├── requirements.txt  pip dependencies
└── logs/             Auto-created on first launch
    └── smarthome_log.csv
```

---

## Serial input format

The GUI consumes JSON lines emitted by the Host ESP's `handle_report_home()`:

```json
{"type":"sensor_report","sender":"leak_sensor","message":"LEAK:3100","trail":[11,5,1],"health":{"temp":24,"battery":87,"uptime":3600},"timestamp":null}
```

| Field | Notes |
|---|---|
| `type` | Currently always `sensor_report`. The GUI also recognizes `sensor_data`, `health`, `alert`, `discovery` (used by demo packets and reserved for future use). |
| `sender` | Peer name from the host's peer list (e.g. `leak_sensor`, `air_quality`, `room_occup`). Not a MAC. |
| `message` | Sensor-specific text the GUI parses with regex. Recognized prefixes: |
| | • `T:..C H:..% L:..lux PIR:0/1` — environmental + occupancy |
| | • `LEAK:<adc>` — water leak ADC reading |
| | • `CAM:PERSON:<conf>` / `CAM:CLEAR` — camera person detection |
| `trail` | Hop trail (list of node IDs). Not yet displayed. |
| `health` | Optional `{temp, battery, uptime}`. Battery shown as `%`, uptime as seconds. |
| `timestamp` | The GUI overwrites this with the local clock on receipt. |

Lines that don't start with `{` are silently dropped.

---

## Tabs

| # | Tab | Purpose |
|---|---|---|
| 1 | 📊 Dashboard | One card per node — live values, sparklines (temp/humidity), battery, uptime, last-seen, stale indicator |
| 2 | 📡 Live Log | Color-coded scrolling table of every parsed packet |
| 3 | 🚨 Alerts | Filtered view of alerts (leak detected, explicit `alert` types). Counted in status bar. |
| 4 | 🔬 Sensors | Per-sensor checkboxes — currently filters `LEAK:` and `CAM:` packets |
| 5 | ⚙️  Settings | Port, baud, log directory, log filename, logging on/off — applied without restart |
| 6 | 📋 Log | Raw text view of the last 500 entries |

Cards turn red and gain a `⚠ STALE` badge if a node hasn't reported in
`STALE_THRESHOLD` seconds (default 15).

---

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `1`–`6` | Switch tabs |
| `Ctrl + L` | Clear live table + reset message count |
| `Ctrl + P` | Pause / resume display (data still queues in background) |
| `Ctrl + R` | Disconnect and reconnect using current settings |
| `Ctrl + C` | Quit |

---

## Setup

```bash
cd GUI
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

Defaults live in `config.py` (port `COM7`, baud `115200`, log dir `./logs`).
Edit there or change them at runtime via the Settings tab.

---

## Run

**Live mode** — connects to the Host ESP over USB:

```bash
python GUI.py
```

**Demo mode** — injects fake packets so you can see the UI without hardware:

```bash
python GUI.py --demo
```

Once the app is up:
1. Settings tab → confirm port (use **Scan Ports** to auto-detect)
2. Dashboard or Live Log tab → press **Connect**
3. Cards will appear as nodes check in.

---

## CSV log format

```csv
timestamp,type,sender,message,temp,battery,uptime
12:34:56,sensor_report,leak_sensor,LEAK:3100,,87,3600
12:34:58,sensor_report,room_occup,T:22.5C H:48% PIR:1,24,86,3660
```

`temp/battery/uptime` come from the optional `health` block; blank if absent.

To change the log destination at runtime: Settings tab → update fields →
**Save Settings**. The current file is closed and a new one opened
immediately, no data loss.

---

## Configuration knobs (`config.py`)

| Constant | Default | Purpose |
|---|---|---|
| `DEFAULT_PORT` | `"COM7"` | Serial port |
| `DEFAULT_BAUDRATE` | `115200` | Must match Host ESP UART |
| `AVAILABLE_SENSORS` | `[temperature, humidity, motion, pressure, leak, camera]` | Sensors tab checkboxes |
| `DEFAULT_LOG_DIR`, `DEFAULT_LOG_FILENAME` | `./logs/`, `smarthome_log.csv` | CSV output |
| `LOG_ENABLED` | `True` | Logger starts on |
| `STALE_THRESHOLD` | `15` | Seconds before a card goes stale |
| `MAX_HISTORY` | `14` | Sparkline data points kept per node |
| `LEAK_THRESHOLD` | `1000` | ADC value above which `LEAK:` packets become alerts. Must match `leak_sensor/main.py`. |
| `ROW_COLORS` | dict | Live-log row coloring per `type` |

---

## Troubleshooting

**No data appears**
- Check the Host ESP is plugged into the listed port — Settings → Scan Ports
- Confirm baud rate is `115200`
- The host must be in `LOCAL_HOP == 0` mode and have peers reporting
- Lines must start with `{` — anything else is dropped silently

**Permission denied on Linux/macOS**
```bash
sudo usermod -aG dialout $USER     # log out and back in
```

**Garbled rendering**
- Use a terminal with 256-color or true-color: Windows Terminal, iTerm2, Alacritty, Kitty
- Minimum 80×24

---

## Dependencies

| Package | Purpose |
|---|---|
| textual | TUI framework |
| pyserial | USB serial I/O |
| rich | Terminal styling (transitive via Textual) |

---

## Known limitations

- Hop trail received in JSON but not displayed yet
- No outbound command path — provisioning (`ADD`, `SYNC`, `SETNAME`) still requires raw serial via PuTTY/screen
- Air-quality VOC/CO2 fields not extracted by the dashboard regex yet
- `esp32_to_PC.py` is legacy (superseded by `SerialReader` inside `GUI.py`) and slated for removal
