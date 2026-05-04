import os
import csv

from config import DEFAULT_LOG_DIR, DEFAULT_LOG_FILENAME, LOG_ENABLED


class DataLogger:
    """CSV logger for parsed mesh packets. Hot-swappable destination."""

    FIELDNAMES = ["timestamp", "type", "sender", "message", "temp", "battery", "uptime"]

    def __init__(self):
        self.enabled  = LOG_ENABLED
        self.log_dir  = DEFAULT_LOG_DIR
        self.filename = DEFAULT_LOG_FILENAME
        self._file    = None
        self._writer  = None

    @property
    def log_path(self) -> str:
        return os.path.join(self.log_dir, self.filename)

    def open(self):
        os.makedirs(self.log_dir, exist_ok=True)
        is_new = not os.path.exists(self.log_path)
        self._file   = open(self.log_path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if is_new:
            self._writer.writerow(self.FIELDNAMES)
            self._file.flush()

    def close(self):
        if self._file:
            self._file.flush()
            self._file.close()
            self._file = self._writer = None

    def set_enabled(self, value: bool):
        self.enabled = value
        if value and self._file is None:
            self.open()
        elif not value:
            self.close()

    def change_destination(self, new_dir: str = None, new_filename: str = None):
        self.close()
        if new_dir:      self.log_dir  = new_dir
        if new_filename: self.filename = new_filename
        if self.enabled:
            self.open()

    def log(self, data: dict):
        if not self.enabled or self._writer is None:
            return
        health = data.get("health", {}) or {}
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
