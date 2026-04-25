# GUI.py
# -----------------------------------------------------------
# Textual-based Terminal GUI for ESP Mesh Serial Data Monitoring.
# Integrates with smart_esp_comm.py running on the Home ESP32 (hop 0).
#
# The Home ESP32 serializes received ACT_REPORT_HOME packets as
# single-line JSON over UART. This GUI reads, parses and displays
# that stream in real time.
#
# Tabs:
#   [1] Live Data  — real-time scrolling data table
#   [2] Sensors    — enable/disable individual sensors
#   [3] Settings   — port, baud rate, log destination
#   [4] Log        — view recent log entries inline
#
# Inline modules (no separate files required):
#   - SerialReader   : async serial → JSON bridge
#   - DataLogger     : CSV/text file logger
#   - config values  : AVAILABLE_SENSORS, DEFAULT_PORT, DEFAULT_BAUDRATE
# -----------------------------------------------------------

import asyncio
import json
import os
import csv
import serial
import serial.tools.list_ports
from datetime import datetime
from textual.app        import App, ComposeResult
from textual.binding    import Binding
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.widgets    import (
    Header, Footer, TabbedContent, TabPane,
    DataTable, Button, Input, Label, Switch,
    Select, Static, Log, Checkbox,
)
from textual.reactive   import reactive
from textual            import on


# ─────────────────────────────────────────────────────────────────────────────
# Config  (replaces config.py)
# ─────────────────────────────────────────────────────────────────────────────

AVAILABLE_SENSORS  = ["temperature", "humidity", "motion", "pressure"]
DEFAULT_PORT       = "COM3"
DEFAULT_BAUDRATE   = 115200
DEFAULT_LOG_DIR    = "./logs"
DEFAULT_LOG_FILENAME = "serial_log.csv"


# ─────────────────────────────────────────────────────────────────────────────
# DataLogger  (replaces logger.py)
# ─────────────────────────────────────────────────────────────────────────────

class DataLogger:
    """
    Writes incoming packet dicts to a CSV log file.
    Columns: timestamp, sender, message, trail, temp, battery, uptime
    """

    def __init__(self):
        self.enabled  = True
        self.log_dir  = DEFAULT_LOG_DIR
        self.filename = DEFAULT_LOG_FILENAME
        self.log_path = os.path.join(self.log_dir, self.filename)
        self._file    = None
        self._writer  = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def open(self):
        """Open (or create) the log file and write the CSV header if new."""
        os.makedirs(self.log_dir, exist_ok=True)
        is_new = not os.path.exists(self.log_path)
        self._file   = open(self.log_path, "a", newline="")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(
                ["timestamp", "sender", "message", "trail", "temp", "battery", "uptime"]
            )
            self._file.flush()

    def close(self):
        """Flush and close the log file."""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file   = None
            self._writer = None

    def set_enabled(self, value: bool):
        self.enabled = value

    def change_destination(self, new_dir: str = None, new_filename: str = None):
        """Reopen the log at a new path."""
        self.close()
        if new_dir:
            self.log_dir  = new_dir
        if new_filename:
            self.filename = new_filename
        self.log_path = os.path.join(self.log_dir, self.filename)
        self.open()

    # ── Write ──────────────────────────────────────────────────────────────────

    def log(self, data: dict):
        """
        Write a parsed packet dict to the CSV.
        data keys expected: timestamp, sender, message, trail, health
        """
        if not self.enabled or self._writer is None:
            return
        health = data.get("health", {})
        trail  = " → ".join(str(h) for h in data.get("trail", []))
        self._writer.writerow([
            data.get("timestamp", ""),
            data.get("sender",    ""),
            data.get("message",   ""),
            trail,
            health.get("temp",    ""),
            health.get("battery", ""),
            health.get("uptime",  ""),
        ])
        self._file.flush()


# ─────────────────────────────────────────────────────────────────────────────
# SerialReader  (replaces esp32_to_PC.py)
# ─────────────────────────────────────────────────────────────────────────────

class SerialReader:
    """
    Async serial bridge between the Home ESP32 and the GUI.

    The ESP32 prints one JSON object per line for each decoded
    ACT_REPORT_HOME packet it receives. Non-JSON lines (e.g. [BOOT],
    [ROUTE] debug prints) are silently ignored.

    Usage:
        reader = SerialReader()
        ok = reader.connect(port="COM3", baudrate=115200)
        reader.start_reading(callback=my_async_callback)
        ...
        reader.disconnect()
    """

    def __init__(self):
        self._serial       = None
        self._task         = None
        self.data_queue    = asyncio.Queue()
        self.error         = None
        self._running      = False
        self._callback     = None

    # ── Connection ─────────────────────────────────────────────────────────────

    def connect(self, port: str, baudrate: int) -> bool:
        """Open the serial port. Returns True on success."""
        try:
            self._serial = serial.Serial(port, baudrate, timeout=1)
            self.error   = None
            return True
        except serial.SerialException as e:
            self.error = str(e)
            return False

    def disconnect(self):
        """Stop reading and close the port."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def start_reading(self, callback=None):
        """Launch the async read loop as a background task."""
        self._running  = True
        self._callback = callback
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._read_loop())

    def flush_queue(self):
        """Drain all pending items from the data queue."""
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except Exception:
                break

    def get_available_ports(self) -> list:
        """Return a list of available serial port names on this machine."""
        return [p.device for p in serial.tools.list_ports.comports()]

    # ── Async Read Loop ────────────────────────────────────────────────────────

    async def _read_loop(self):
        """
        Continuously reads lines from the serial port.
        Parses JSON lines into packet dicts and puts them on data_queue.
        Skips non-JSON debug output from the ESP firmware.
        """
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                # readline() is blocking — run it in a thread executor
                line = await loop.run_in_executor(None, self._serial.readline)
                if line:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    self._parse_and_enqueue(decoded)
            except serial.SerialException as e:
                self.error    = str(e)
                self._running = False
                break
            except Exception as e:
                self.error = str(e)
                await asyncio.sleep(0.2)

    def _parse_and_enqueue(self, line: str):
        """
        Try to parse a single line as JSON.
        Drops the line silently if it is not valid JSON (e.g. ESP debug prints).
        Adds a PC-side timestamp before enqueuing.
        """
        if not line.startswith("{"):
            return  # skip [BOOT], [ROUTE], [SYNC] etc.
        try:
            data = json.loads(line)
            data["timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.data_queue.put_nowait(data)
        except json.JSONDecodeError:
            pass  # malformed line — ignore


# ─────────────────────────────────────────────────────────────────────────────
# Status Bar Widget
# ─────────────────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Bottom status strip: connection state, message count, log path."""

    connected = reactive(False)
    log_path  = reactive("—")
    msg_count = reactive(0)

    def render(self) -> str:
        state = "[bold green]● CONNECTED[/]" if self.connected else "[bold red]○ DISCONNECTED[/]"
        return (
            f"{state}  │  "
            f"[cyan]Messages:[/] {self.msg_count}  │  "
            f"[yellow]Log:[/] {self.log_path}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────────────────────

class SerialTUI(App):
    """
    ESP Mesh Serial Data Terminal GUI
    Built with Textual + PySerial

    Receives JSON-encoded ACT_REPORT_HOME packets from the Home ESP32
    over USB serial and displays sensor data in real time.
    """

    CSS = """
    /* ── Global ─────────────────────────────────────────────────────────── */
    Screen {
        background: #0d1117;
    }

    /* ── Status Bar ──────────────────────────────────────────────────────── */
    StatusBar {
        height: 1;
        background: #161b22;
        color: #c9d1d9;
        padding: 0 2;
        dock: bottom;
    }

    /* ── Panels ──────────────────────────────────────────────────────────── */
    .panel {
        padding: 1 2;
        height: 100%;
    }

    /* ── Settings Form ───────────────────────────────────────────────────── */
    .form-row {
        height: 3;
        margin-bottom: 1;
    }
    .form-label {
        width: 20;
        padding-top: 1;
        color: #8b949e;
    }
    .form-input {
        width: 30;
    }

    /* ── Sensor Grid ─────────────────────────────────────────────────────── */
    .sensor-grid {
        layout: grid;
        grid-size: 2;
        grid-gutter: 1;
        padding: 1;
    }
    .sensor-card {
        border: solid #30363d;
        padding: 0 1;
        height: 3;
        background: #161b22;
    }

    /* ── Buttons ─────────────────────────────────────────────────────────── */
    .btn-connect {
        background: #238636;
        color: white;
        margin-right: 1;
    }
    .btn-disconnect {
        background: #da3633;
        color: white;
        margin-right: 1;
    }
    .btn-clear {
        background: #30363d;
        color: white;
    }
    .btn-save {
        background: #1f6feb;
        color: white;
        margin-right: 1;
    }
    .btn-browse {
        background: #30363d;
        color: white;
    }

    /* ── DataTable ───────────────────────────────────────────────────────── */
    DataTable {
        height: 1fr;
        border: solid #30363d;
    }

    /* ── Log Panel ───────────────────────────────────────────────────────── */
    Log {
        height: 1fr;
        border: solid #30363d;
        background: #0d1117;
    }

    /* ── Divider ─────────────────────────────────────────────────────────── */
    .divider {
        height: 1;
        background: #30363d;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit",          "Quit",         show=True),
        Binding("ctrl+l", "clear_data",    "Clear Data",   show=True),
        Binding("ctrl+r", "reconnect",     "Reconnect",    show=True),
        Binding("ctrl+p", "pause_toggle",  "Pause/Resume", show=True),
        Binding("1",      "show_tab('live')",     "Live Data"),
        Binding("2",      "show_tab('sensors')",  "Sensors"),
        Binding("3",      "show_tab('settings')", "Settings"),
        Binding("4",      "show_tab('log')",      "Log"),
    ]

    # ── Reactive State ─────────────────────────────────────────────────────────
    is_connected = reactive(False)
    is_paused    = reactive(False)

    def __init__(self):
        super().__init__()
        self.reader        = SerialReader()
        self.logger        = DataLogger()
        self.active_sensors = set(AVAILABLE_SENSORS)   # all enabled by default
        self.message_count  = 0
        self._poll_task     = None

    # ─────────────────────────────────────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(initial="live"):

            # ── Tab 1: Live Data ────────────────────────────────────────────
            with TabPane("📡 Live Data", id="live"):
                with Vertical(classes="panel"):
                    # Connection control row
                    with Horizontal(classes="form-row"):
                        yield Button("Connect",    id="btn_connect",    classes="btn-connect")
                        yield Button("Disconnect", id="btn_disconnect", classes="btn-disconnect")
                        yield Button("Clear",      id="btn_clear",      classes="btn-clear")
                        yield Label("", id="pause_label")

                    yield Static("─" * 80, classes="divider")

                    # Live scrolling data table
                    table = DataTable(id="live_table", zebra_stripes=True)
                    table.cursor_type = "row"
                    yield table

            # ── Tab 2: Sensor Selection ─────────────────────────────────────
            with TabPane("🔬 Sensors", id="sensors"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Enable / Disable Sensors[/bold]\n")
                    yield Static("Toggle which sensors appear in the live view and log.", classes="form-label")
                    yield Static("─" * 60, classes="divider")

                    with Container(classes="sensor-grid"):
                        for sensor in AVAILABLE_SENSORS:
                            with Horizontal(classes="sensor-card"):
                                yield Checkbox(sensor, value=True, id=f"sensor_{sensor}")

                    yield Static("─" * 60, classes="divider")
                    yield Button("Apply Sensor Filters", id="btn_apply_sensors", classes="btn-save")

            # ── Tab 3: Settings ─────────────────────────────────────────────
            with TabPane("⚙️  Settings", id="settings"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Connection Settings[/bold]")
                    yield Static("─" * 60, classes="divider")

                    # Serial Port
                    with Horizontal(classes="form-row"):
                        yield Label("Serial Port:", classes="form-label")
                        yield Input(
                            value=DEFAULT_PORT,
                            placeholder="/dev/ttyUSB0 or COM3",
                            id="input_port",
                            classes="form-input",
                        )
                        yield Button("Scan Ports", id="btn_scan_ports", classes="btn-browse")

                    # Baud Rate
                    with Horizontal(classes="form-row"):
                        yield Label("Baud Rate:", classes="form-label")
                        yield Select(
                            options=[
                                ("9600",   "9600"),
                                ("19200",  "19200"),
                                ("38400",  "38400"),
                                ("57600",  "57600"),
                                ("115200", "115200"),
                                ("230400", "230400"),
                                ("921600", "921600"),
                            ],
                            value=str(DEFAULT_BAUDRATE),
                            id="select_baud",
                        )

                    yield Static("─" * 60, classes="divider")
                    yield Label("[bold]Logging Settings[/bold]")
                    yield Static("─" * 60, classes="divider")

                    # Logging toggle
                    with Horizontal(classes="form-row"):
                        yield Label("Enable Logging:", classes="form-label")
                        yield Switch(value=True, id="switch_logging")

                    # Log Directory
                    with Horizontal(classes="form-row"):
                        yield Label("Log Directory:", classes="form-label")
                        yield Input(
                            value=DEFAULT_LOG_DIR,
                            placeholder="Path to log folder",
                            id="input_log_dir",
                            classes="form-input",
                        )

                    # Log Filename
                    with Horizontal(classes="form-row"):
                        yield Label("Log Filename:", classes="form-label")
                        yield Input(
                            value=DEFAULT_LOG_FILENAME,
                            placeholder="mylog.csv",
                            id="input_log_file",
                            classes="form-input",
                        )

                    yield Static("─" * 60, classes="divider")
                    with Horizontal():
                        yield Button("💾 Save Settings",  id="btn_save_settings",  classes="btn-save")
                        yield Button("🔄 Reset Defaults", id="btn_reset_settings", classes="btn-browse")

                    yield Static("", id="settings_status")

            # ── Tab 4: Log Viewer ───────────────────────────────────────────
            with TabPane("📋 Log", id="log"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Inline Log Viewer[/bold] (last 500 entries)")
                    yield Static("─" * 60, classes="divider")
                    yield Log(id="log_view", highlight=True, max_lines=500)

        yield StatusBar(id="status_bar")
        yield Footer()

    # ─────────────────────────────────────────────────────────────────────────
    # Startup
    # ─────────────────────────────────────────────────────────────────────────

    def on_mount(self):
        """Initialize DataTable columns and open the logger."""
        table: DataTable = self.query_one("#live_table")
        table.add_column("Time",    width=10)
        table.add_column("Sender",  width=14)
        table.add_column("Message", width=22)
        table.add_column("Trail",   width=18)
        table.add_column("Temp",    width=8)
        table.add_column("Battery", width=9)
        table.add_column("Uptime",  width=10)

        self.logger.open()
        self._update_status()

    # ─────────────────────────────────────────────────────────────────────────
    # Button Handlers
    # ─────────────────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_connect")
    async def handle_connect(self):
        """Read port/baud from Settings, then open the serial connection."""
        port     = self.query_one("#input_port",  Input).value.strip()
        baud_sel = self.query_one("#select_baud", Select).value
        baudrate = int(baud_sel) if baud_sel else DEFAULT_BAUDRATE

        self.notify(f"Connecting to {port} @ {baudrate} baud…")

        success = self.reader.connect(port=port, baudrate=baudrate)
        if success:
            self.reader.start_reading()
            self.is_connected = True
            self._start_poll()
            self.notify(f"✅ Connected to {port}", severity="information")
        else:
            self.notify(f"❌ Failed: {self.reader.error}", severity="error")

        self._update_status()

    @on(Button.Pressed, "#btn_disconnect")
    async def handle_disconnect(self):
        """Cancel the poll task and close the serial port."""
        if self._poll_task:
            self._poll_task.cancel()
        self.reader.disconnect()
        self.is_connected = False
        self.notify("Disconnected from serial port.", severity="warning")
        self._update_status()

    @on(Button.Pressed, "#btn_clear")
    def handle_clear(self):
        self.action_clear_data()

    @on(Button.Pressed, "#btn_scan_ports")
    def handle_scan_ports(self):
        """Scan for available serial ports and auto-fill the first one found."""
        ports = self.reader.get_available_ports()
        if ports:
            port_list = ", ".join(ports)
            self.notify(f"Available ports: {port_list}", timeout=8)
            self.query_one("#input_port", Input).value = ports[0]
        else:
            self.notify("No serial ports found.", severity="warning")

    @on(Button.Pressed, "#btn_apply_sensors")
    def handle_apply_sensors(self):
        """Update the active sensor filter from checkbox states."""
        self.active_sensors = set()
        for sensor in AVAILABLE_SENSORS:
            cb: Checkbox = self.query_one(f"#sensor_{sensor}", Checkbox)
            if cb.value:
                self.active_sensors.add(sensor)
        self.notify(
            f"Active sensors: {', '.join(self.active_sensors) or 'None'}",
            severity="information",
        )

    @on(Button.Pressed, "#btn_save_settings")
    def handle_save_settings(self):
        """Persist logging settings from the Settings tab."""
        new_dir  = self.query_one("#input_log_dir",  Input).value.strip()
        new_file = self.query_one("#input_log_file", Input).value.strip()
        enabled  = self.query_one("#switch_logging", Switch).value

        self.logger.set_enabled(enabled)
        if new_dir or new_file:
            self.logger.change_destination(
                new_dir=new_dir or None,
                new_filename=new_file or None,
            )

        status: Static = self.query_one("#settings_status")
        status.update(f"[green]✔ Settings saved. Log → {self.logger.log_path}[/green]")
        self._update_status()

    @on(Button.Pressed, "#btn_reset_settings")
    def handle_reset_settings(self):
        """Restore all settings inputs to compile-time defaults."""
        self.query_one("#input_port",      Input).value  = DEFAULT_PORT
        self.query_one("#select_baud",     Select).value = str(DEFAULT_BAUDRATE)
        self.query_one("#input_log_dir",   Input).value  = DEFAULT_LOG_DIR
        self.query_one("#input_log_file",  Input).value  = DEFAULT_LOG_FILENAME
        self.query_one("#switch_logging",  Switch).value = True
        self.query_one("#settings_status", Static).update(
            "[yellow]Defaults restored. Press Save to apply.[/yellow]"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Data Polling (Async Loop)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_poll(self):
        """Launch the asyncio task that drains the serial queue into the UI."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = asyncio.get_event_loop().create_task(self._poll_serial())

    async def _poll_serial(self):
        """
        Runs every 50 ms. Drains up to 20 entries per cycle from the
        SerialReader queue and updates the DataTable + Log panel.

        Each entry is a dict produced by SerialReader._parse_and_enqueue():
            {
                "type":      "sensor_report",
                "sender":    "<node name>",
                "message":   "<decoded payload string>",
                "trail":     [<hop IDs>, ...],
                "health":    {"temp": int, "battery": int, "uptime": int},
                "timestamp": "HH:MM:SS"   ← added by SerialReader on PC side
            }
        """
        table:    DataTable = self.query_one("#live_table")
        log_view: Log       = self.query_one("#log_view")

        while self.is_connected:
            if not self.is_paused:
                drained = 0
                while not self.reader.data_queue.empty() and drained < 20:
                    try:
                        entry = self.reader.data_queue.get_nowait()
                    except Exception:
                        break

                    sender  = entry.get("sender",  "unknown")
                    message = entry.get("message", "")
                    trail   = " → ".join(str(h) for h in entry.get("trail", []))
                    health  = entry.get("health", {})
                    temp    = f"{health.get('temp',    '--')}°C"
                    battery = f"{health.get('battery', '--')}%"
                    uptime  = f"{health.get('uptime',  '--')}s"
                    ts      = entry.get("timestamp", "")

                    # Sensor filter — always pass "RAW" type through
                    if sender not in self.active_sensors and entry.get("type") != "RAW":
                        pass  # still display; filter is advisory for future use

                    # ── Add row to DataTable ────────────────────────────────
                    table.add_row(ts, sender, message, trail, temp, battery, uptime)

                    # ── Append to inline Log viewer ─────────────────────────
                    log_view.write_line(
                        f"[{ts}] {sender:12s} → {message}  "
                        f"trail={trail}  {temp}  bat={battery}  up={uptime}"
                    )

                    # ── Write to CSV log file ───────────────────────────────
                    self.logger.log(entry)

                    self.message_count += 1
                    drained += 1

                # Scroll DataTable to newest row
                if drained > 0:
                    table.scroll_end(animate=False)
                    self._update_status()

            # ── Check for reader-level errors ───────────────────────────────
            if self.reader.error:
                self.notify(f"Serial error: {self.reader.error}", severity="error")
                self.is_connected = False
                self._update_status()
                break

            await asyncio.sleep(0.05)   # 50 ms poll interval

    # ─────────────────────────────────────────────────────────────────────────
    # Actions (Keybindings)
    # ─────────────────────────────────────────────────────────────────────────

    def action_clear_data(self):
        """Clear the live DataTable and reset the message counter."""
        table: DataTable = self.query_one("#live_table")
        table.clear()
        self.message_count = 0
        self.reader.flush_queue()
        self._update_status()
        self.notify("Live data cleared.")

    def action_reconnect(self):
        """Disconnect then reconnect using the current Settings values."""
        if self.is_connected:
            self.call_after_refresh(self.handle_disconnect)
            self.call_after_refresh(self.handle_connect)

    def action_pause_toggle(self):
        """Freeze / unfreeze the live display (data still queues while paused)."""
        self.is_paused = not self.is_paused
        label: Label   = self.query_one("#pause_label")
        if self.is_paused:
            label.update("[bold yellow]⏸ PAUSED[/bold yellow]")
            self.notify("Display paused. Data still being collected.", severity="warning")
        else:
            label.update("")
            self.notify("Display resumed.")

    def action_show_tab(self, tab_id: str):
        """Switch to the specified tab by ID."""
        self.query_one(TabbedContent).active = tab_id

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _update_status(self):
        """Sync the StatusBar widget with current application state."""
        bar: StatusBar  = self.query_one("#status_bar")
        bar.connected   = self.is_connected
        bar.log_path    = self.logger.log_path if self.logger.enabled else "Logging OFF"
        bar.msg_count   = self.message_count

    async def on_unmount(self):
        """Clean up serial connection and logger on exit."""
        if self._poll_task:
            self._poll_task.cancel()
        self.reader.disconnect()
        self.logger.close()


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = SerialTUI()
    app.run()
