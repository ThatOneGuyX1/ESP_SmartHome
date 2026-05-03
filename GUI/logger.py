# logger.py
# -----------------------------------------------------------
# CSV and plain-text logger with runtime-changeable destination.
# -----------------------------------------------------------

import os
import csv
from datetime import datetime
from config import DEFAULT_LOG_DIR, DEFAULT_LOG_FILENAME, LOG_ENABLED


class DataLogger:
    """
    Logs serial data entries to a CSV file.
    The log destination (directory + filename) can be changed at runtime.
    """

    def __init__(self):
        self.enabled      = LOG_ENABLED
        self.log_dir      = DEFAULT_LOG_DIR
        self.log_filename = DEFAULT_LOG_FILENAME
        self._file        = None
        self._writer      = None
        self._fieldnames  = ["timestamp", "sensor", "value", "raw"]

    # ----------------------------------------------------------
    # File Management
    # ----------------------------------------------------------

    @property
    def log_path(self) -> str:
        return os.path.join(self.log_dir, self.log_filename)

    def open(self):
        """Open/create the log file (appends if exists)."""
        os.makedirs(self.log_dir, exist_ok=True)
        new_file = not os.path.exists(self.log_path)
        self._file   = open(self.log_path, "a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self._fieldnames)
        if new_file:
            self._writer.writeheader()

    def close(self):
        """Flush and close the log file."""
        if self._file:
            self._file.flush()
            self._file.close()
            self._file   = None
            self._writer = None

    def change_destination(self, new_dir: str = None, new_filename: str = None):
        """
        Hot-swap the log file at runtime.
        Closes the current file and opens a new one at the given path.
        """
        self.close()
        if new_dir:
            self.log_dir = new_dir
        if new_filename:
            self.log_filename = new_filename
        if self.enabled:
            self.open()

    # ----------------------------------------------------------
    # Writing
    # ----------------------------------------------------------

    def log(self, entry: dict):
        """Write a parsed data entry to the log file."""
        if not self.enabled or self._writer is None:
            return
        try:
            self._writer.writerow({
                "timestamp": entry.get("timestamp", ""),
                "sensor":    entry.get("sensor",    ""),
                "value":     entry.get("value",     ""),
                "raw":       entry.get("raw",       ""),
            })
            self._file.flush()
        except Exception as e:
            pass  # Don't crash the UI for a log error

    def set_enabled(self, state: bool):
        self.enabled = state
        if state and self._file is None:
            self.open()
        elif not state:
            self.close()