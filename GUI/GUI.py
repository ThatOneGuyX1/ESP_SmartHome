# main.py
# -----------------------------------------------------------
# Textual-based Terminal GUI for Serial Data Monitoring.
#
# Tabs:
#   [1] Live Data  — real-time scrolling data table
#   [2] Sensors    — enable/disable individual sensors
#   [3] Settings   — port, baud rate, log destination
#   [4] Log        — view recent log entries inline
# -----------------------------------------------------------

import asyncio
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

from serial_import import SerialReader
from logger        import DataLogger
from config        import AVAILABLE_SENSORS, DEFAULT_PORT, DEFAULT_BAUDRATE


# ─────────────────────────────────────────────────────────────
# Status Bar Widget
# ─────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Bottom status strip showing connection state & log path."""

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


# ─────────────────────────────────────────────────────────────
# Main Application
# ─────────────────────────────────────────────────────────────

class SerialTUI(App):
    """
    Serial Data Terminal GUI
    Built with Textual + PySerial
    """

    CSS = """
    /* ── Global ─────────────────────────────────────── */
    Screen {
        background: #0d1117;
    }

    /* ── Status Bar ──────────────────────────────────── */
    StatusBar {
        height: 1;
        background: #161b22;
        color: #c9d1d9;
        padding: 0 2;
        dock: bottom;
    }

    /* ── Panels ──────────────────────────────────────── */
    .panel {
        padding: 1 2;
        height: 100%;
    }

    /* ── Settings Form ───────────────────────────────── */
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

    /* ── Sensor Grid ─────────────────────────────────── */
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

    /* ── Buttons ─────────────────────────────────────── */
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

    /* ── DataTable ───────────────────────────────────── */
    DataTable {
        height: 1fr;
        border: solid #30363d;
    }

    /* ── Log Panel ───────────────────────────────────── */
    Log {
        height: 1fr;
        border: solid #30363d;
        background: #0d1117;
    }

    /* ── Divider ─────────────────────────────────────── */
    .divider {
        height: 1;
        background: #30363d;
        margin: 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit",         "Quit",        show=True),
        Binding("ctrl+l", "clear_data",   "Clear Data",  show=True),
        Binding("ctrl+r", "reconnect",    "Reconnect",   show=True),
        Binding("ctrl+p", "pause_toggle", "Pause/Resume",show=True),
        Binding("1",      "show_tab('live')",    "Live Data"),
        Binding("2",      "show_tab('sensors')", "Sensors"),
        Binding("3",      "show_tab('settings')","Settings"),
        Binding("4",      "show_tab('log')",     "Log"),
    ]

    # ── Reactive State ────────────────────────────────────────
    is_connected = reactive(False)
    is_paused    = reactive(False)

    def __init__(self):
        super().__init__()
        self.reader           = SerialReader()
        self.logger           = DataLogger()
        self.active_sensors   = set(AVAILABLE_SENSORS)   # all enabled by default
        self.message_count    = 0
        self._poll_task       = None

    # ─────────────────────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent(initial="live"):

            # ── Tab 1: Live Data ──────────────────────────────
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

            # ── Tab 2: Sensor Selection ───────────────────────
            with TabPane("🔬 Sensors", id="sensors"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Enable / Disable Sensors[/bold]\n")
                    yield Static("Toggle which sensors appear in the live view and log.", classes="form-label")
                    yield Static("─" * 60, classes="divider")

                    with Container(classes="sensor-grid"):
                        for sensor in AVAILABLE_SENSORS:
                            with Horizontal(classes="sensor-card"):
                                cb = Checkbox(sensor, value=True, id=f"sensor_{sensor}")
                                yield cb

                    yield Static("─" * 60, classes="divider")
                    yield Button("Apply Sensor Filters", id="btn_apply_sensors", classes="btn-save")

            # ── Tab 3: Settings ───────────────────────────────
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
                            value="./logs",
                            placeholder="Path to log folder",
                            id="input_log_dir",
                            classes="form-input",
                        )

                    # Log Filename
                    with Horizontal(classes="form-row"):
                        yield Label("Log Filename:", classes="form-label")
                        yield Input(
                            value="serial_log.csv",
                            placeholder="mylog.csv",
                            id="input_log_file",
                            classes="form-input",
                        )

                    yield Static("─" * 60, classes="divider")
                    with Horizontal():
                        yield Button("💾 Save Settings", id="btn_save_settings", classes="btn-save")
                        yield Button("🔄 Reset Defaults", id="btn_reset_settings", classes="btn-browse")

                    yield Static("", id="settings_status")

            # ── Tab 4: Log Viewer ─────────────────────────────
            with TabPane("📋 Log", id="log"):
                with Vertical(classes="panel"):
                    yield Label("[bold]Inline Log Viewer[/bold] (last 500 entries)")
                    yield Static("─" * 60, classes="divider")
                    yield Log(id="log_view", highlight=True, max_lines=500)

        yield StatusBar(id="status_bar")
        yield Footer()

    # ─────────────────────────────────────────────────────────
    # Startup
    # ─────────────────────────────────────────────────────────

    def on_mount(self):
        """Initialize table columns and open the logger."""
        table: DataTable = self.query_one("#live_table")
        table.add_column("Time",    width=12)
        table.add_column("Sensor",  width=16)
        table.add_column("Value",   width=20)
        table.add_column("Raw",     width=40)

        self.logger.open()
        self._update_status()

    # ─────────────────────────────────────────────────────────
    # Button Handlers
    # ─────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn_connect")
    async def handle_connect(self):
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
        ports = self.reader.get_available_ports()
        if ports:
            port_list = ", ".join(ports)
            self.notify(f"Available ports: {port_list}", timeout=8)
            # Auto-fill first found port
            self.query_one("#input_port", Input).value = ports[0]
        else:
            self.notify("No serial ports found.", severity="warning")

    @on(Button.Pressed, "#btn_apply_sensors")
    def handle_apply_sensors(self):
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
        from config import DEFAULT_PORT, DEFAULT_BAUDRATE, DEFAULT_LOG_DIR, DEFAULT_LOG_FILENAME
        self.query_one("#input_port",     Input).value = DEFAULT_PORT
        self.query_one("#select_baud",    Select).value = str(DEFAULT_BAUDRATE)
        self.query_one("#input_log_dir",  Input).value = DEFAULT_LOG_DIR
        self.query_one("#input_log_file", Input).value = DEFAULT_LOG_FILENAME
        self.query_one("#switch_logging", Switch).value = True
        self.query_one("#settings_status", Static).update("[yellow]Defaults restored. Press Save to apply.[/yellow]")

    # ─────────────────────────────────────────────────────────
    # Data Polling (Async Loop)
    # ─────────────────────────────────────────────────────────

    def _start_poll(self):
        """Start the asyncio task that drains the serial queue."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = asyncio.get_event_loop().create_task(self._poll_serial())

    async def _poll_serial(self):
        """
        Runs every 50 ms. Drains up to 20 entries per cycle from
        the serial queue and updates the DataTable + Log panel.
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

                    # Sensor filter
                    if entry["sensor"] not in self.active_sensors and entry["sensor"] != "RAW":
                        drained += 1
                        continue

                    # Add to DataTable
                    table.add_row(
                        entry["timestamp"],
                        entry["sensor"],
                        entry["value"],
                        entry["raw"],
                    )

                    # Log inline viewer
                    log_view.write_line(
                        f"[{entry['timestamp']}] {entry['sensor']:12s} → {entry['value']}"
                    )

                    # Write to CSV
                    self.logger.log(entry)

                    self.message_count += 1
                    drained += 1

                # Scroll to bottom
                if drained > 0:
                    table.scroll_end(animate=False)
                    self._update_status()

                # Check for reader errors
                if self.reader.error:
                    self.notify(f"Serial error: {self.reader.error}", severity="error")
                    self.is_connected = False
                    self._update_status()
                    break

            await asyncio.sleep(0.05)  # 50 ms poll interval

    # ─────────────────────────────────────────────────────────
    # Actions (Keybindings)
    # ─────────────────────────────────────────────────────────

    def action_clear_data(self):
        table: DataTable = self.query_one("#live_table")
        table.clear()
        self.message_count = 0
        self.reader.flush_queue()
        self._update_status()
        self.notify("Live data cleared.")

    def action_reconnect(self):
        if self.is_connected:
            self.call_after_refresh(self.handle_disconnect)
        self.call_after_refresh(self.handle_connect)

    def action_pause_toggle(self):
        self.is_paused = not self.is_paused
        label: Label   = self.query_one("#pause_label")
        if self.is_paused:
            label.update("[bold yellow]⏸ PAUSED[/bold yellow]")
            self.notify("Display paused. Data still being collected.", severity="warning")
        else:
            label.update("")
            self.notify("Display resumed.")

    def action_show_tab(self, tab_id: str):
        self.query_one(TabbedContent).active = tab_id

    # ─────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────

    def _update_status(self):
        bar: StatusBar      = self.query_one("#status_bar")
        bar.connected       = self.is_connected
        bar.log_path        = self.logger.log_path if self.logger.enabled else "Logging OFF"
        bar.msg_count       = self.message_count

    async def on_unmount(self):
        """Clean up on exit."""
        if self._poll_task:
            self._poll_task.cancel()
        self.reader.disconnect()
        self.logger.close()


# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = SerialTUI()
    app.run()