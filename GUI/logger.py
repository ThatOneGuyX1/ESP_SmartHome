import os
import csv
import json
from datetime import datetime

from config import DEFAULT_LOG_DIR, DEFAULT_LOG_FILENAME, LOG_ENABLED


def _session_filename(base: str) -> str:
    """Insert a session timestamp before the extension, e.g.
    'smarthome_log.csv' -> 'smarthome_log_2026-05-05_14-32.csv'."""
    root, ext = os.path.splitext(base)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"{root}_{stamp}{ext}"


class DataLogger:
    """Logs parsed mesh packets to CSV and a parallel JSONL file. Hot-swappable destination.

    Each program launch gets its own timestamped pair of files so individual
    sessions don't bleed into each other.
    """

    FIELDNAMES = ["timestamp", "type", "sender", "message", "temp", "battery", "uptime"]

    def __init__(self):
        self.enabled  = LOG_ENABLED
        self.log_dir  = DEFAULT_LOG_DIR
        self.filename = _session_filename(DEFAULT_LOG_FILENAME)
        self._csv_file    = None
        self._csv_writer  = None
        self._jsonl_file  = None

    @property
    def log_path(self) -> str:
        return os.path.join(self.log_dir, self.filename)

    @property
    def jsonl_path(self) -> str:
        base, _ = os.path.splitext(self.log_path)
        return base + ".jsonl"

    def open(self):
        os.makedirs(self.log_dir, exist_ok=True)
        is_new = not os.path.exists(self.log_path)
        self._csv_file   = open(self.log_path, "a", newline="", encoding="utf-8")
        self._csv_writer = csv.writer(self._csv_file)
        if is_new:
            self._csv_writer.writerow(self.FIELDNAMES)
            self._csv_file.flush()
        self._jsonl_file = open(self.jsonl_path, "a", encoding="utf-8")

    def close(self):
        if self._csv_file:
            self._csv_file.flush()
            self._csv_file.close()
            self._csv_file = self._csv_writer = None
        if self._jsonl_file:
            self._jsonl_file.flush()
            self._jsonl_file.close()
            self._jsonl_file = None

    def set_enabled(self, value: bool):
        self.enabled = value
        if value and self._csv_file is None:
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
        if not self.enabled or self._csv_writer is None:
            return
        health = data.get("health", {}) or {}
        self._csv_writer.writerow([
            data.get("timestamp", ""),
            data.get("type",      ""),
            data.get("sender",    ""),
            data.get("message",   ""),
            health.get("temp",    ""),
            health.get("battery", ""),
            health.get("uptime",  ""),
        ])
        self._csv_file.flush()
        if self._jsonl_file:
            self._jsonl_file.write(json.dumps(data) + "\n")
            self._jsonl_file.flush()
