# serial_import.py
# -----------------------------------------------------------
# Serial data reader and parser. This module runs in a
# background thread and feeds data into a shared queue.
# -----------------------------------------------------------

import serial
import serial.tools.list_ports
import threading
import queue
import time
from datetime import datetime
from config import DEFAULT_PORT, DEFAULT_BAUDRATE, DEFAULT_TIMEOUT, DATA_DELIMITER


class SerialReader:
    """
    Manages the serial connection and reads data into a thread-safe queue.
    Parses lines formatted as "SensorName:Value".
    """

    def __init__(self):
        self.port       = DEFAULT_PORT
        self.baudrate   = DEFAULT_BAUDRATE
        self.timeout    = DEFAULT_TIMEOUT
        self.ser        = None
        self.data_queue = queue.Queue(maxsize=500)
        self._thread    = None
        self._running   = False
        self.error      = None

    # ----------------------------------------------------------
    # Connection Management
    # ----------------------------------------------------------

    def connect(self, port: str = None, baudrate: int = None) -> bool:
        """Open the serial port. Returns True on success."""
        self.port     = port or self.port
        self.baudrate = baudrate or self.baudrate
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            self.error = None
            return True
        except serial.SerialException as e:
            self.error = str(e)
            return False

    def disconnect(self):
        """Stop reading and close the serial port."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    # ----------------------------------------------------------
    # Background Reader Thread
    # ----------------------------------------------------------

    def start_reading(self):
        """Launch the background reader thread."""
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(
            target=self._read_loop,
            daemon=True,
            name="SerialReaderThread",
        )
        self._thread.start()

    def stop_reading(self):
        self._running = False

    def _read_loop(self):
        """Internal loop: reads lines from serial, parses, enqueues."""
        while self._running and self.is_connected():
            try:
                raw = self.ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                parsed = self._parse_line(line)
                if not self.data_queue.full():
                    self.data_queue.put_nowait(parsed)

            except serial.SerialException as e:
                self.error = str(e)
                self._running = False
            except Exception as e:
                self.error = f"Read error: {e}"

    # ----------------------------------------------------------
    # Parser
    # ----------------------------------------------------------

    def _parse_line(self, line: str) -> dict:
        """
        Parse a raw serial line into a structured dict.
        Expected: "SensorName:Value"
        Falls back to raw if format is unexpected.
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        if DATA_DELIMITER in line:
            parts  = line.split(DATA_DELIMITER, 1)
            sensor = parts[0].strip()
            value  = parts[1].strip()
        else:
            sensor = "RAW"
            value  = line

        return {
            "timestamp": timestamp,
            "sensor":    sensor,
            "value":     value,
            "raw":       line,
        }

    # ----------------------------------------------------------
    # Utilities
    # ----------------------------------------------------------

    def get_available_ports(self) -> list[str]:
        """Return a list of available serial port names."""
        return [p.device for p in serial.tools.list_ports.comports()]

    def flush_queue(self):
        """Clear all queued data."""
        while not self.data_queue.empty():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break