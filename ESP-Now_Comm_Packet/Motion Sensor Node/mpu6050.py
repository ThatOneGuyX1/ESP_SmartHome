# mpu6050.py
# Minimal MPU6050 driver for MicroPython.

class MPU6050:
    ADDRESS = 0x68

    REG_PWR_MGMT_1 = 0x6B
    REG_ACCEL_XOUT_H = 0x3B
    REG_TEMP_OUT_H = 0x41
    REG_GYRO_XOUT_H = 0x43

    ACCEL_SCALE = 16384.0   # +/- 2g
    GYRO_SCALE = 131.0      # +/- 250 deg/s
    G_TO_MS2 = 9.80665

    def __init__(self, i2c, address=ADDRESS):
        self.i2c = i2c
        self.address = address

        # Wake up MPU6050
        self.i2c.writeto_mem(self.address, self.REG_PWR_MGMT_1, b'\x00')

    def _read_i16(self, reg):
        data = self.i2c.readfrom_mem(self.address, reg, 2)
        value = (data[0] << 8) | data[1]

        if value & 0x8000:
            value -= 65536

        return value

    def read_accel_g(self):
        ax = self._read_i16(self.REG_ACCEL_XOUT_H) / self.ACCEL_SCALE
        ay = self._read_i16(self.REG_ACCEL_XOUT_H + 2) / self.ACCEL_SCALE
        az = self._read_i16(self.REG_ACCEL_XOUT_H + 4) / self.ACCEL_SCALE

        return ax, ay, az

    def read_accel_ms2(self):
        ax, ay, az = self.read_accel_g()

        return (
            ax * self.G_TO_MS2,
            ay * self.G_TO_MS2,
            az * self.G_TO_MS2
        )

    def read_gyro_dps(self):
        gx = self._read_i16(self.REG_GYRO_XOUT_H) / self.GYRO_SCALE
        gy = self._read_i16(self.REG_GYRO_XOUT_H + 2) / self.GYRO_SCALE
        gz = self._read_i16(self.REG_GYRO_XOUT_H + 4) / self.GYRO_SCALE

        return gx, gy, gz

    def read_temp_c(self):
        raw = self._read_i16(self.REG_TEMP_OUT_H)
        return (raw / 340.0) + 36.53