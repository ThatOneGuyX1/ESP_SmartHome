# esp32_to_PC.py
import serial
import json
import asyncio
from datetime import datetime


class SerialReader:
    """
    Async serial reader that connects to the Home ESP32 over USB/UART.
    Parses JSON lines from the ESP and emits structured dicts to the GUI.
    """

    def __init__(self, port: str, baudrate: int, callback):
        """
        Args:
            port:     e.g. "COM3" or "/dev/ttyUSB0"
            baudrate: e.g. 115200
            callback: async function called with each parsed packet dict
        """
        self.port = port
        self.baudrate = baudrate
        self.callback = callback
        self._running = False
        self._serial = None

    def connect(self):
        self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
        self._running = True
        print(f"[SERIAL] Connected to {self.port} @ {self.baudrate} baud")

    def disconnect(self):
        self._running = False
        if self._serial and self._serial.is_open:
            self._serial.close()
        print("[SERIAL] Disconnected.")

    async def run(self):
        """Main async read loop. Call as an asyncio task."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                line = await loop.run_in_executor(
                    None, self._serial.readline
                )
                if line:
                    decoded = line.decode("utf-8", errors="replace").strip()
                    self._parse_line(decoded)
            except Exception as e:
                print(f"[SERIAL] Read error: {e}")
                await asyncio.sleep(0.5)

    def _parse_line(self, line: str):
        """Try to parse a JSON line; skip debug/log lines."""
        if not line.startswith("{"):
            return  # Skip ESP debug prints like [BOOT], [ROUTE], etc.
        try:
            data = json.loads(line)
            data["timestamp"] = datetime.now().strftime("%H:%M:%S")
            asyncio.create_task(self.callback(data))
        except json.JSONDecodeError:
            print(f"[SERIAL] Non-JSON line: {line}")