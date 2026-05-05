# max17048_driver.py
# Minimal MAX17048 LiPo/LiIon fuel gauge driver for MicroPython.
# I2C address: 0x36.

class MAX17048:
    ADDRESS = 0x36
    REG_VCELL = 0x02
    REG_SOC = 0x04
    REG_VERSION = 0x08
    REG_MODE = 0x06
    REG_CONFIG = 0x0C
    REG_COMMAND = 0xFE

    def __init__(self, i2c, address=ADDRESS):
        self.i2c = i2c
        self.address = address

    def _read_reg16(self, reg):
        data = self.i2c.readfrom_mem(self.address, reg, 2)
        return (data[0] << 8) | data[1]

    def _write_reg16(self, reg, value):
        data = bytes([(value >> 8) & 0xFF, value & 0xFF])
        self.i2c.writeto_mem(self.address, reg, data)

    def read_version(self):
        return self._read_reg16(self.REG_VERSION)

    def read_voltage_mv(self):
        # VCELL: 12-bit value left-aligned in 16-bit register.
        # LSB after shifting is 1.25 mV.
        raw = self._read_reg16(self.REG_VCELL)
        return ((raw >> 4) * 1.25)

    def read_voltage(self):
        return self.read_voltage_mv() / 1000.0

    @property
    def voltage(self):
        return self.read_voltage()

    @property
    def cell_voltage(self):
        return self.read_voltage()

    def read_soc(self):
        # SOC MSB = integer %, LSB = 1/256 %.
        raw = self._read_reg16(self.REG_SOC)
        soc = ((raw >> 8) & 0xFF) + ((raw & 0xFF) / 256.0)

        # Clamp SOC to valid battery percentage range.
        # MAX17048 can sometimes report slightly above 100%.
        if soc < 0:
            soc = 0

        if soc > 100:
            soc = 100

        return soc

    @property
    def soc(self):
        return self.read_soc()

    @property
    def cell_percent(self):
        return self.read_soc()

    def quick_start(self):
        # Optional: restarts fuel-gauge algorithm. Do not call continuously.
        self._write_reg16(self.REG_MODE, 0x4000)

    def reset(self):
        # Optional: power-on reset command.
        self._write_reg16(self.REG_COMMAND, 0x5400)