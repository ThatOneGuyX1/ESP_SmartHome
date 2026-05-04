# bh1750.py
# Minimal BH1750 driver for MicroPython.

import time

class BH1750:
    ADDR = 0x23
    POWER_ON = 0x01
    RESET = 0x07
    ONE_TIME_HIGH_RES = 0x20

    def __init__(self, i2c, addr=ADDR):
        self.i2c = i2c
        self.addr = addr
        self.i2c.writeto(self.addr, bytes([self.POWER_ON]))
        time.sleep_ms(10)
        self.i2c.writeto(self.addr, bytes([self.RESET]))
        time.sleep_ms(10)

    def read_lux(self):
        self.i2c.writeto(self.addr, bytes([self.ONE_TIME_HIGH_RES]))
        time.sleep_ms(180)
        data = self.i2c.readfrom(self.addr, 2)
        raw = (data[0] << 8) | data[1]
        return raw / 1.2
