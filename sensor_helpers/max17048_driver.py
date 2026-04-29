# max17048_driver.py
# Minimal MicroPython MAX17048 driver for voltage and SOC.

import time


class MAX17048:
    ADDRESS = 0x36

    REG_VCELL = 0x02
    REG_SOC = 0x04
    REG_MODE = 0x06
    REG_VERSION = 0x08
    REG_CONFIG = 0x0C
    REG_CRATE = 0x16
    REG_STATUS = 0x1A
    REG_CMD = 0xFE

    def __init__(self, i2c, address=0x36):
        self.i2c = i2c
        self.address = address

    def _read_u16(self, reg):
        self.i2c.writeto(self.address, bytes([reg]))
        data = self.i2c.readfrom(self.address, 2)
        return (data[0] << 8) | data[1]

    def _write_u16(self, reg, value):
        self.i2c.writeto(self.address, bytes([reg, (value >> 8) & 0xFF, value & 0xFF]))

    def cell_voltage(self):
        # MAX17048 VCELL register: use upper 12 bits; 1.25 mV per LSB for single-cell VCELL.
        raw = self._read_u16(self.REG_VCELL)
        return ((raw >> 4) * 1.25) / 1000.0

    def cell_percent(self):
        # SOC register is percent in MSB plus fractional 1/256 percent in LSB.
        raw = self._read_u16(self.REG_SOC)
        percent = (raw >> 8) + ((raw & 0xFF) / 256.0)
        if percent < 0:
            percent = 0
        if percent > 100:
            percent = 100
        return percent

    def charge_rate(self):
        # CRATE LSB is approximately 0.208 percent/hour.
        raw = self._read_u16(self.REG_CRATE)
        if raw & 0x8000:
            raw -= 0x10000
        return raw * 0.208

    def version(self):
        return self._read_u16(self.REG_VERSION)

    def status(self):
        return self._read_u16(self.REG_STATUS)

    def quick_start(self):
        # Do not call continuously. Useful only after a stable battery connection.
        self._write_u16(self.REG_MODE, 0x4000)
        time.sleep_ms(200)
