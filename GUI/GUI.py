# GUI.py
# -----------------------------------------------------------
# Textual-based Terminal GUI for ESP Mesh Serial Data Monitoring.
#
# Tabs:
#   [1] Dashboard  — live node cards with sparkline trends
#   [2] Live Log   — color-coded scrolling event table
#   [3] Alerts     — dedicated alert history with count
#   [4] Sensors    — enable/disable individual sensors
#   [5] Settings   — port, baud rate, log destination
#   [6] Log        — raw inline log viewer
# -----------------------------------------------------------

import asyncio
import json
import os
import re
import csv
import serial
import serial.tools.list_ports
from datetime import datetime
from textual.app        import App, ComposeResult
from textual.binding    import Binding
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.widgets    import (
    Header, TabbedContent, TabPane,
    DataTable, Button, Input, Label, Switch,
    Select, Static, Log, Checkbox,
)
from textual.reactive   import reactive
from textual            import on


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

AVAILABLE_SENSORS    = ["temperature", "humidity", "motion", "pressure", "leak", "camera"]
DEFAULT_PORT         = "COM7"
DEFAULT_BAUDRATE     = 115200
DEFAULT_LOG_DIR      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
DEFAULT_LOG_FILENAME = "smarthome_log.csv"

STALE_THRESHOLD = 15    # seconds with no packet before a node is marked stale
MAX_HISTORY     = 14    # number of sparkline data points kept per node
SPARK_CHARS     = "▁▂▃▄▅▆▇█"
LEAK_THRESHOLD  = 1000  # ADC 0-4095 — must match leak_sensor/main.py

ROW_COLORS = {
    "sensor_data":   "white",
    "sensor_report": "white",
    "health":        "cyan",
    "alert":         "bold red",
    "discovery":     "green",
}


# ─────────────────────────────────────────────────────────────────────────────
# DataLogger
# ─────────────────────────────────────────────────────────────────────────────

class DataLogger:
    def __init__(self):
        self.enabled  = True
        self.log_dir  = DEFAULT_LOG_DIR
        self.filename = DEFAULT_LOG_FILENAME
        self.log_path = os.path.join(self.log_dir, self.filename)
        self._file    = None
        self._writer  = None

    def open(self):
        os.makedirs(self.log_dir, exist_ok=True)
        is_new = not os.path.exists(self.log_path)
        self._file   = open(self.log_path, "a", newline="")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(
                ["timestamp", "type", "sender", "message", "temp", "battery", "uptime"]
            )
            self._file.flush()

    def close(self):
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = self._writer = None

    def set_enabled(self, value: bool):
        self.enabled = value

    def change_destination(self, new_dir=None, new_filename=None):
        self.close()
        if new_dir:      self.log_dir  = new_dir
        if new_filename: self.filename = new_filename
        self.log_path = os.path.join(self.log_dir, self.filename)
        if self.enabled:
            self.open()

    def log(self, data: dict):
        if not self.enabled or self._writer is None:
            return
        health = data.get("health", {})
        self._writer.writerow([
            data.get("timestamp", ""),
            data.get("type",      ""),
            data.get("sender",    ""),
            data.get("message",   ""),
            health.get("temp",    ""),
            health.get("battery", ""),
            health.get("uptime",  ""),
        ])
        self._file.flush()


# ─────────────────────────────────────────────────────────────────────────────
# SerialReader
# ─────────────────────────────────────────────────────────────────────────────

class SerialReader:
    def __init__(self):
        self._serial    = None
        self._task      = None
        self.data_queue = asyncio.Queue()
        self.error      = None
        self._running   = False

    def connect(self, port: str, baudrate: int) -> bool:
        try:
            self._serial = serial.Serial(port, baudrate, timeout=1)
            self.error   = None
            return True
        except serial.SerialException as e:
            self.error = str(e)
            return False

    def disconnect(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def start_reading(self):
        self._running = True
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._read_loop())

    def flush_queue(self):
        while not self.data_queue.empty():
            try:   self.data_queue.get_nowait()
            except Exception: break

    def get_available_ports(self) -> list:
        return [p.device for p in serial.tools.list_ports.comports()]

    async def _read_loop(self):
        loop = asyncio.get_event_loop()
        while self._running:
            try:
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
        if not line.startswith("{"):
            return
        try:
            data = json.loads(line)
            data["timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.data_queue.put_nowait(data)
        except json.JSONDecodeError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# NodeCard  — live summary card for one sensor node
# ─────────────────────────────────────────────────────────────────────────────

class NodeCard(Static):
    DEFAULT_CSS = """
    NodeCard {
        border: solid #30363d;
        background: #161b22;
        padding: 1 2;
        margin: 0 1 1 0;
        width: 42;
        height: auto;
    }
    NodeCard.stale {
        border: solid #da3633;
        background: #1a0c0c;
    }
    """

    def __init__(self, mac: str, **kwargs):
        super().__init__(**kwargs)
        self.mac   = mac
        self._state = {
            "node_type": "UNKNOWN",
            "temp":      "—",
            "humidity":  "—",
            "light":     "—",
            "occupancy": "—",
            "battery":   "—",
            "uptime":    "—",
            "last_seen": "—",
            "alert":     "",
            "leak":      "—",
            "person":    "—",
        }
        self._temp_history: list[float] = []
        self._hum_history:  list[float] = []
        self._last_seen_dt = None
        self._is_stale     = False

    @staticmethod
    def _sparkline(values: list[float]) -> str:
        if len(values) < 2:
            return "─" * MAX_HISTORY
        lo, hi = min(values), max(values)
        span = hi - lo or 1.0
        return "".join(SPARK_CHARS[int((v - lo) / span * 7)] for v in values)

    def absorb(self, msg_type: str, entry: dict):
        s = self._state
        s["last_seen"] = entry.get("timestamp", "—")
        msg = entry.get("message", "")

        if msg_type == "discovery":
            s["node_type"] = msg.split()[0] if msg else "UNKNOWN"
            s["alert"] = ""

        elif msg_type == "sensor_data":
            m = re.search(r'T:([\d.]+)C', msg)
            if m:
                s["temp"] = m.group(1) + "°C"
                self._temp_history.append(float(m.group(1)))
                if len(self._temp_history) > MAX_HISTORY:
                    self._temp_history.pop(0)
            m = re.search(r'H:([\d.]+)%', msg)
            if m:
                s["humidity"] = m.group(1) + "%"
                self._hum_history.append(float(m.group(1)))
                if len(self._hum_history) > MAX_HISTORY:
                    self._hum_history.pop(0)
            m = re.search(r'L:(\d+)lux', msg)
            if m: s["light"] = m.group(1) + " lux"
            m = re.search(r'PIR:(\d)', msg)
            if m: s["occupancy"] = "OCCUPIED" if m.group(1) == "1" else "VACANT"

        elif msg_type == "health":
            h = entry.get("health", {})
            bat = h.get("battery", "")
            upt = h.get("uptime",  "")
            if bat != "": s["battery"] = f"{bat}%"
            if upt != "": s["uptime"]  = f"{upt}s"

        elif msg_type == "alert":
            s["alert"] = msg

        elif msg_type == "sensor_report":
            if msg.startswith("LEAK:"):
                try:
                    raw = int(msg.split(":")[1])
                    if raw >= LEAK_THRESHOLD:
                        s["leak"]  = f"DETECTED (ADC:{raw})"
                        s["alert"] = f"LEAK DETECTED (ADC:{raw})"
                    else:
                        s["leak"]  = f"DRY (ADC:{raw})"
                        s["alert"] = ""
                except (ValueError, IndexError):
                    pass
            elif msg.startswith("CAM:PERSON:"):
                try:
                    conf = int(msg.split(":")[2])
                    s["person"] = f"PERSON ({conf}%)"
                except (ValueError, IndexError):
                    s["person"] = "PERSON"
            elif msg == "CAM:CLEAR":
                s["person"] = "CLEAR"

        # Clear stale status on any incoming packet
        self._last_seen_dt = datetime.now()
        if self._is_stale:
            self._is_stale = False
            self.remove_class("stale")

        self.update(self._build_markup())

    def check_stale(self):
        """Called periodically; marks card stale if no packet within STALE_THRESHOLD."""
        if self._last_seen_dt is None:
            return
        now_stale = (datetime.now() - self._last_seen_dt).total_seconds() > STALE_THRESHOLD
        if now_stale != self._is_stale:
            self._is_stale = now_stale
            if now_stale:
                self.add_class("stale")
            else:
                self.remove_class("stale")
            self.update(self._build_markup())

    def _build_markup(self) -> str:
        s = self._state
        if self._is_stale:
            status = "[bold red]⚠ STALE[/bold red]"
        else:
            status = "[bold green]● LIVE[/bold green]"
        alert_line = f"\n[bold red]⚠  {s['alert']}[/bold red]" if s["alert"] else ""
        t_spark = self._sparkline(self._temp_history)
        h_spark = self._sparkline(self._hum_history)
        leak_val = s["leak"]
        if "DETECTED" in leak_val:
            leak_disp = f"[bold red]{leak_val}[/bold red]"
        elif "DRY" in leak_val:
            leak_disp = f"[green]{leak_val}[/green]"
        else:
            leak_disp = leak_val

        person_val = s["person"]
        if "PERSON" in person_val:
            person_disp = f"[yellow]{person_val}[/yellow]"
        elif person_val == "CLEAR":
            person_disp = f"[green]{person_val}[/green]"
        else:
            person_disp = person_val

        return (
            f"[bold cyan]{self.mac}[/bold cyan]  {status}\n"
            f"[dim]{s['node_type']}[/dim]\n"
            f"{'─' * 38}\n"
            f"[yellow]Temp:[/yellow]      {s['temp']:8}  [dim]{t_spark}[/dim]\n"
            f"[yellow]Humidity:[/yellow]  {s['humidity']:8}  [dim]{h_spark}[/dim]\n"
            f"[yellow]Light:[/yellow]     {s['light']}\n"
            f"[yellow]Motion:[/yellow]    {s['occupancy']}\n"
            f"[yellow]Leak:[/yellow]      {leak_disp}\n"
            f"[yellow]Camera:[/yellow]    {person_disp}\n"
            f"{'─' * 38}\n"
            f"[dim]Battery: {s['battery']}   Uptime: {s['uptime']}[/dim]\n"
            f"[dim]Last seen: {s['last_seen']}[/dim]"
            f"{alert_line}"
        )

    def render(self) -> str:
        return self._build_markup()


# ─────────────────────────────────────────────────────────────────────────────
# Status Bar
# ─────────────────────────────────────────────────────────────────────────────

class StatusBar(Static):
    connected   = reactive(False)
    log_path    = reactive("—")
    msg_count   = reactive(0)
    alert_count = reactive(0)

    def render(self) -> str:
        state = "[bold green]● CONNECTED[/]" if self.connected else "[bold red]○ DISCONNECTED[/]"
        alerts = (
            f"  │  [bold red]🚨 {self.alert_count} alert{'s' if self.alert_count != 1 else ''}[/bold red]"
            if self.alert_count > 0 else ""
        )
        return (
            f"{state}  │  "
            f"[cyan]Messages:[/] {self.msg_count}"
            f"{alerts}  │  "
            f"[yellow]Log:[/] {self.log_path}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────────────────────

class SerialTUI(App):

    CSS = """
    Screen { background: #0d1117; }

    StatusBar {
        height: 1; dock: bottom;
        background: #161b22; color: #c9d1d9; padding: 0 2;
    }

    .panel { padding: 1 2; height: 1fr; }

    .form-row    { height: 3; margin-bottom: 1; }
    .form-label  { width: 20; padding-top: 1; color: #8b949e; }
    .form-input  { width: 30; }

.btn-connect    { background: #238636; color: white; margin-right: 1; }
    .btn-disconnect { background: #da3633; color: white; margin-right: 1; }
    .btn-clear      { background: #30363d; color: white; }
    .btn-save       { background: #1f6feb; color: white; margin-right: 1; }
    .btn-browse     { background: #30363d; color: white; }

    #dashboard_cards { height: auto; }

    DataTable { height: 1fr; border: solid #30363d; }

    Log {
        height: 1fr; border: solid #30363d; background: #0d1117;
    }

    .divider { height: 1; background: #30363d; margin: 1 0; }

    .no_nodes { color: #8b949e; padding: 2; }

    .alert-header { color: #f85149; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit",          "Quit",         show=True),
        Binding("ctrl+l", "clear_data",    "Clear Data",   show=True),
        Binding("ctrl+r", "reconnect",     "Reconnect",    show=True),
        Binding("ctrl+p", "pause_toggle",  "Pause/Resume", show=True),
        Binding("1", "show_tab('dashboard')", "Dashboard"),
        Binding("2", "show_tab('live')",      "Live Log"),
        Binding("3", "show_tab('alerts')",    "Alerts"),
        Binding("4", "show_tab('sensors')",   "Sensors"),
        Binding("5", "show_tab('settings')",  "Settings"),
        Binding("6", "show_tab('log')",       "Log"),
    ]

    is_connected = reactive(False)
    is_paused    = reactive(False)

    DEMO_PACKETS = [
        {"type": "sensor_report", "sender": "00:4B:12:BD:58:C0", "message": "LEAK:3100",           "trail": [11], "health": {}},
        {"type": "sensor_report", "sender": "00:4B:12:BD:58:C0", "message": "CAM:PERSON:87",        "trail": [10], "health": {}},
        {"type": "sensor_report", "sender": "00:4B:12:BD:58:C0", "message": "CAM:CLEAR",            "trail": [10], "health": {}},
        {"type": "sensor_report", "sender": "00:4B:12:BD:58:C0", "message": "LEAK:200",             "trail": [11], "health": {}},
        {"type": "sensor_data",   "sender": "B8:F8:62:D5:44:04", "message": "T:22.5C H:48% PIR:1", "trail": [2],  "health": {"battery": 87, "uptime": 3600}},
        {"type": "sensor_data",   "sender": "B8:F8:62:D5:44:04", "message": "T:23.1C H:46% PIR:0", "trail": [2],  "health": {"battery": 86, "uptime": 3660}},
    ]

    def __init__(self, demo: bool = False):
        super().__init__()
        self._demo          = demo
        self.reader         = SerialReader()
        self.logger         = DataLogger()
        self.active_sensors = set(AVAILABLE_SENSORS)
        self.message_count  = 0
        self.alert_count    = 0
        self._poll_task     = None
        self._node_cards: dict[str, NodeCard] = {}

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(initial="dashboard"):

            # ── Tab 1: Dashboard ─────────────────────────────────────────────
            with TabPane("📊 Dashboard", id="dashboard"):
                with ScrollableContainer(classes="panel"):
                    with Horizontal(classes="form-row"):
                        yield Button("Connect",    id="btn_connect",    classes="btn-connect")
                        yield Button("Disconnect", id="btn_disconnect", classes="btn-disconnect")
                        yield Label("", id="pause_label")
                    yield Static("─" * 80, classes="divider")
                    yield Label("[bold]Live Node Status[/bold]  —  cards appear as nodes check in")
                    yield Horizontal(id="dashboard_cards")
                    yield Static(
                        "No nodes connected yet. Start the gateway and sensor nodes.",
                        id="no_nodes_hint",
                        classes="no_nodes",
                    )

            # ── Tab 2: Live Log ──────────────────────────────────────────────
            with TabPane("📡 Live Log", id="live"):
                with Vertical(classes="panel"):
                    with Horizontal(classes="form-row"):
                        yield Button("Connect",    id="btn_connect2",    classes="btn-connect")
                        yield Button("Disconnect", id="btn_disconnect2", classes="btn-disconnect")
                        yield Button("Clear",      id="btn_clear",       classes="btn-clear")
                        yield Label("", id="pause_label2")
                    yield Static("─" * 80, classes="divider")
                    table = DataTable(id="live_table", zebra_stripes=True)
                    table.cursor_type = "row"
                    yield table

            # ── Tab 3: Alerts ────────────────────────────────────────────────
            with TabPane("🚨 Alerts", id="alerts"):
                with Vertical(classes="panel"):
                    with Horizontal(classes="form-row"):
                        yield Label("", id="alert_count_label", classes="alert-header")
                        yield Button("Clear Alerts", id="btn_clear_alerts", classes="btn-clear")
                    yield Static("─" * 80, classes="divider")
                    alerts_table = DataTable(id="alerts_table", zebra_stripes=True)
                    alerts_table.cursor_type = "row"
                    yield alerts_table

            # ── Tab 4: Sensor Selection ──────────────────────────────────────
            with TabPane("🔬 Sensors", id="sensors"):
                with ScrollableContainer(classes="panel"):
                    yield Label("[bold]Enable / Disable Sensors[/bold]")
                    yield Static("─" * 60, classes="divider")
                    for sensor in AVAILABLE_SENSORS:
                        yield Checkbox(sensor, value=True, id=f"sensor_{sensor}")
                    yield Static("─" * 60, classes="divider")
                    yield Button("Apply Filters", id="btn_apply_sensors", classes="btn-save")

            # ── Tab 5: Settings ──────────────────────────────────────────────
            with TabPane("⚙️  Settings", id="settings"):
                with ScrollableContainer(classes="panel"):
                    yield Label("[bold]Connection Settings[/bold]")
                    yield Static("─" * 60, classes="divider")

                    with Horizontal(classes="form-row"):
                        yield Label("Serial Port:",  classes="form-label")
                        yield Input(value=DEFAULT_PORT, placeholder="COM4", id="input_port", classes="form-input")
                        yield Button("Scan Ports", id="btn_scan_ports", classes="btn-browse")

                    with Horizontal(classes="form-row"):
                        yield Label("Baud Rate:", classes="form-label")
                        yield Select(
                            options=[("9600","9600"),("19200","19200"),("38400","38400"),
                                     ("57600","57600"),("115200","115200"),
                                     ("230400","230400"),("921600","921600")],
                            value=str(DEFAULT_BAUDRATE),
                            id="select_baud",
                        )

                    yield Static("─" * 60, classes="divider")
                    yield Label("[bold]Logging Settings[/bold]")
                    yield Static("─" * 60, classes="divider")

                    with Horizontal(classes="form-row"):
                        yield Label("Enable Logging:", classes="form-label")
                        yield Switch(value=True, id="switch_logging")

                    with Horizontal(classes="form-row"):
                        yield Label("Log Directory:", classes="form-label")
                        yield Input(value=DEFAULT_LOG_DIR,      id="input_log_dir",  classes="form-input")

                    with Horizontal(classes="form-row"):
                        yield Label("Log Filename:",  classes="form-label")
                        yield Input(value=DEFAULT_LOG_FILENAME, id="input_log_file", classes="form-input")

                    yield Static("─" * 60, classes="divider")
                    with Horizontal():
                        yield Button("💾 Save Settings",  id="btn_save_settings",  classes="btn-save")
                        yield Button("🔄 Reset Defaults", id="btn_reset_settings", classes="btn-browse")
                    yield Static("", id="settings_status")

            # ── Tab 6: Raw Log ───────────────────────────────────────────────
            with TabPane("📋 Log", id="log"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Raw Log[/bold] (last 500 entries)")
                    yield Static("─" * 60, classes="divider")
                    yield Log(id="log_view", highlight=True, max_lines=500)

        yield StatusBar(id="status_bar")

    # ── Startup ───────────────────────────────────────────────────────────────

    def on_mount(self):
        table: DataTable = self.query_one("#live_table")
        table.add_column("Time",    width=10)
        table.add_column("Type",    width=13)
        table.add_column("Sender",  width=19)
        table.add_column("Message", width=32)
        table.add_column("Temp",    width=8)
        table.add_column("Battery", width=8)
        table.add_column("Uptime",  width=8)

        alerts_table: DataTable = self.query_one("#alerts_table")
        alerts_table.add_column("Time",    width=10)
        alerts_table.add_column("Sender",  width=19)
        alerts_table.add_column("Alert",   width=50)

        self.logger.open()
        self._update_status()
        self.set_interval(5, self._check_stale_nodes)
        self.notify(f"Logging to: {self.logger.log_path}", timeout=6)
        if self._demo:
            self.is_connected = True
            self._start_poll()
            self.run_worker(self._inject_demo_packets(), exclusive=False)
            self.notify("Demo mode active — fake packets incoming", timeout=5)

    # ── Button handlers ───────────────────────────────────────────────────────

    async def _do_connect(self):
        port     = self.query_one("#input_port",  Input).value.strip()
        baud_sel = self.query_one("#select_baud", Select).value
        baudrate = int(baud_sel) if baud_sel else DEFAULT_BAUDRATE
        self.notify(f"Connecting to {port} @ {baudrate} baud…")
        if self.reader.connect(port=port, baudrate=baudrate):
            self.reader.start_reading()
            self.is_connected = True
            self._start_poll()
            self.notify(f"✅ Connected to {port}", severity="information")
        else:
            self.notify(f"❌ {self.reader.error}", severity="error")
        self._update_status()

    async def _do_disconnect(self):
        if self._poll_task:
            self._poll_task.cancel()
        self.reader.disconnect()
        self.is_connected = False
        self.notify("Disconnected.", severity="warning")
        self._update_status()

    @on(Button.Pressed, "#btn_connect")
    async def handle_connect(self):  await self._do_connect()

    @on(Button.Pressed, "#btn_connect2")
    async def handle_connect2(self): await self._do_connect()

    @on(Button.Pressed, "#btn_disconnect")
    async def handle_disconnect(self):  await self._do_disconnect()

    @on(Button.Pressed, "#btn_disconnect2")
    async def handle_disconnect2(self): await self._do_disconnect()

    @on(Button.Pressed, "#btn_clear")
    def handle_clear(self): self.action_clear_data()

    @on(Button.Pressed, "#btn_clear_alerts")
    def handle_clear_alerts(self):
        self.query_one("#alerts_table", DataTable).clear()
        self.alert_count = 0
        self.query_one("#alert_count_label", Label).update("")
        self._update_status()
        self.notify("Alerts cleared.")

    @on(Button.Pressed, "#btn_scan_ports")
    def handle_scan_ports(self):
        ports = self.reader.get_available_ports()
        if ports:
            self.notify(f"Ports: {', '.join(ports)}", timeout=8)
            self.query_one("#input_port", Input).value = ports[0]
        else:
            self.notify("No ports found.", severity="warning")

    @on(Button.Pressed, "#btn_apply_sensors")
    def handle_apply_sensors(self):
        self.active_sensors = {
            s for s in AVAILABLE_SENSORS
            if self.query_one(f"#sensor_{s}", Checkbox).value
        }
        self.notify(f"Active: {', '.join(self.active_sensors) or 'None'}")

    @on(Button.Pressed, "#btn_save_settings")
    def handle_save_settings(self):
        self.logger.set_enabled(self.query_one("#switch_logging", Switch).value)
        self.logger.change_destination(
            new_dir=self.query_one("#input_log_dir",  Input).value.strip() or None,
            new_filename=self.query_one("#input_log_file", Input).value.strip() or None,
        )
        self.query_one("#settings_status", Static).update(
            f"[green]✔ Saved. Log → {self.logger.log_path}[/green]"
        )
        self._update_status()

    @on(Button.Pressed, "#btn_reset_settings")
    def handle_reset_settings(self):
        self.query_one("#input_port",      Input).value  = DEFAULT_PORT
        self.query_one("#select_baud",     Select).value = str(DEFAULT_BAUDRATE)
        self.query_one("#input_log_dir",   Input).value  = DEFAULT_LOG_DIR
        self.query_one("#input_log_file",  Input).value  = DEFAULT_LOG_FILENAME
        self.query_one("#switch_logging",  Switch).value = True
        self.query_one("#settings_status", Static).update(
            "[yellow]Defaults restored. Press Save to apply.[/yellow]"
        )

    # ── Polling ───────────────────────────────────────────────────────────────

    def _start_poll(self):
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = asyncio.get_event_loop().create_task(self._poll_serial())

    async def _poll_serial(self):
        table:        DataTable = self.query_one("#live_table")
        alerts_table: DataTable = self.query_one("#alerts_table")
        log_view:     Log       = self.query_one("#log_view")

        while self.is_connected:
            if not self.is_paused:
                drained = 0
                while not self.reader.data_queue.empty() and drained < 20:
                    try:
                        entry = self.reader.data_queue.get_nowait()
                    except Exception:
                        break

                    msg_type = entry.get("type",    "")
                    sender   = entry.get("sender",  "unknown")
                    message  = entry.get("message", "")
                    health   = entry.get("health",  {})
                    ts       = entry.get("timestamp", "")
                    temp     = f"{health.get('temp',    '--')}°C"
                    battery  = f"{health.get('battery', '--')}%"
                    uptime   = f"{health.get('uptime',  '--')}s"

                    # ── Sensor filter (Sensors tab checkboxes) ──────────────
                    if msg_type == "sensor_report":
                        if message.startswith("LEAK:") and "leak" not in self.active_sensors:
                            continue
                        if message.startswith("CAM:") and "camera" not in self.active_sensors:
                            continue

                    # ── Update dashboard card ────────────────────────────────
                    await self._update_node_card(sender, msg_type, entry)

                    # ── Color-coded live table row ───────────────────────────
                    color = ROW_COLORS.get(msg_type, "white")
                    table.add_row(
                        f"[{color}]{ts}[/]",
                        f"[{color}]{msg_type}[/]",
                        f"[{color}]{sender}[/]",
                        f"[{color}]{message}[/]",
                        f"[{color}]{temp}[/]",
                        f"[{color}]{battery}[/]",
                        f"[{color}]{uptime}[/]",
                    )

                    # ── Alerts tab ───────────────────────────────────────────
                    is_alert = msg_type == "alert"
                    if msg_type == "sensor_report" and message.startswith("LEAK:"):
                        try:
                            if int(message.split(":")[1]) >= LEAK_THRESHOLD:
                                is_alert = True
                        except (ValueError, IndexError):
                            pass

                    if is_alert:
                        alerts_table.add_row(
                            f"[bold red]{ts}[/]",
                            f"[bold red]{sender}[/]",
                            f"[bold red]{message}[/]",
                        )
                        alerts_table.scroll_end(animate=False)
                        self.alert_count += 1
                        self.query_one("#alert_count_label", Label).update(
                            f"[bold red]🚨 {self.alert_count} alert"
                            f"{'s' if self.alert_count != 1 else ''}[/bold red]"
                        )

                    # ── Raw log ──────────────────────────────────────────────
                    log_view.write_line(
                        f"[{ts}] [{msg_type}] {sender} → {message}"
                    )

                    self.logger.log(entry)
                    self.message_count += 1
                    drained += 1

                if drained > 0:
                    table.scroll_end(animate=False)
                    self._update_status()

            if self.reader.error:
                self.notify(f"Serial error: {self.reader.error}", severity="error")
                self.is_connected = False
                self._update_status()
                break

            await asyncio.sleep(0.05)

    async def _update_node_card(self, mac: str, msg_type: str, entry: dict):
        """Create a NodeCard on first sight of a new node, then update it."""
        if mac not in self._node_cards:
            card = NodeCard(mac, id=f"node_{mac.replace(':', '_')}")
            self._node_cards[mac] = card
            grid = self.query_one("#dashboard_cards")
            hint = self.query_one("#no_nodes_hint")
            hint.display = False
            await grid.mount(card)
        self._node_cards[mac].absorb(msg_type, entry)

    def _check_stale_nodes(self):
        """Called every 5 s; marks node cards stale if silent too long."""
        for card in self._node_cards.values():
            card.check_stale()

    async def _inject_demo_packets(self):
        await asyncio.sleep(1.5)
        for pkt in self.DEMO_PACKETS:
            pkt["timestamp"] = datetime.now().strftime("%H:%M:%S")
            self.reader.data_queue.put_nowait(dict(pkt))
            await asyncio.sleep(2)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_clear_data(self):
        self.query_one("#live_table", DataTable).clear()
        self.message_count = 0
        self.reader.flush_queue()
        self._update_status()
        self.notify("Live log cleared.")

    def action_reconnect(self):
        if self.is_connected:
            self.call_after_refresh(self._do_disconnect)
        self.call_after_refresh(self._do_connect)

    def action_pause_toggle(self):
        self.is_paused = not self.is_paused
        lbl  = self.query_one("#pause_label",  Label)
        lbl2 = self.query_one("#pause_label2", Label)
        txt  = "[bold yellow]⏸ PAUSED[/bold yellow]" if self.is_paused else ""
        lbl.update(txt)
        lbl2.update(txt)
        if self.is_paused:
            self.notify("Paused. Data still queuing.", severity="warning")
        else:
            self.notify("Resumed.")

    def action_show_tab(self, tab_id: str):
        self.query_one(TabbedContent).active = tab_id

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _update_status(self):
        bar: StatusBar = self.query_one("#status_bar")
        bar.connected   = self.is_connected
        bar.log_path    = self.logger.log_path if self.logger.enabled else "Logging OFF"
        bar.msg_count   = self.message_count
        bar.alert_count = self.alert_count

    async def on_unmount(self):
        if self._poll_task:
            self._poll_task.cancel()
        self.reader.disconnect()
        self.logger.close()


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    SerialTUI("--demo" in sys.argv).run()
