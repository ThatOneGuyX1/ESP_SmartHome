"""
MAX17048 LiPo Fuel Gauge I2C Driver.
Mirrors max17048.c from the C firmware.
"""

ADDR         = 0x36
REG_VCELL    = 0x02   # Battery voltage (78.125 uV/cell)
REG_SOC      = 0x04   # State of charge (%)
REG_VERSION  = 0x08   # Chip version


class MAX17048:
    def __init__(self, i2c):
        self.i2c = i2c
        self._initialized = False

    def _read_reg(self, reg):
        """Read a 16-bit big-endian register."""
        self.i2c.writeto(ADDR, bytes([reg]))
        data = self.i2c.readfrom(ADDR, 2)
        return (data[0] << 8) | data[1]

    def init(self):
        """Verify chip is present by reading VERSION register."""
        self._initialized = False
        try:
            version = self._read_reg(REG_VERSION)
            if version == 0:
                print('[HEALTH] MAX17048: VERSION=0, chip may not be present')
                return False
            self._initialized = True
            print('[HEALTH] MAX17048 detected (version=0x%04X)' % version)
            return True
        except OSError as e:
            print('[HEALTH] MAX17048 not detected:', e)
            return False

    def read_voltage_mv(self):
        """Read battery voltage in millivolts."""
        if not self._initialized:
            return 0
        try:
            raw = self._read_reg(REG_VCELL)
            return (raw * 5) // 64
        except OSError:
            return 0

    def read_soc(self):
        """Read state-of-charge percentage (0-100)."""
        if not self._initialized:
            return 0
        try:
            raw = self._read_reg(REG_SOC)
            soc = raw >> 8
            return min(soc, 100)
        except OSError:
            return 0
