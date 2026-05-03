"""
Sensor Hardware Abstraction Layer.
Mirrors sensor_hal_real.c — I2C drivers for DHT20, BH1750, PIR GPIO.
"""
import machine
import time

import config

# I2C addresses
DHT20_ADDR  = 0x38
BH1750_ADDR = 0x23

# DHT20 commands
DHT20_CMD_TRIGGER = bytes([0xAC, 0x33, 0x00])
DHT20_MEAS_DELAY  = 80   # ms

# BH1750 commands
BH1750_CMD_POWER_ON = bytes([0x01])
BH1750_CMD_HRES_1X  = bytes([0x20])
BH1750_MEAS_DELAY   = 180  # ms


class SensorHAL:
    def __init__(self, i2c=None, pir_pin=None):
        self.i2c = i2c
        self.pir = machine.Pin(
            pir_pin or config.PIR_GPIO_PIN,
            machine.Pin.IN,
            machine.Pin.PULL_DOWN
        )
        self._occupancy = 0

    def init(self):
        """Initialize I2C bus if not provided, check DHT20 calibration, power on BH1750."""
        if self.i2c is None:
            self.i2c = machine.I2C(
                0,
                sda=machine.Pin(config.I2C_SDA_PIN),
                scl=machine.Pin(config.I2C_SCL_PIN),
                freq=config.I2C_FREQ
            )

        print('[SENSOR] I2C: SDA=GPIO%d SCL=GPIO%d %dHz' % (
            config.I2C_SDA_PIN, config.I2C_SCL_PIN, config.I2C_FREQ))

        # Scan I2C bus
        devices = self.i2c.scan()
        print('[SENSOR] I2C devices:', ['0x%02X' % d for d in devices])

        # DHT20 calibration check
        self._dht20_check_calibration()

        # BH1750 power on
        try:
            self.i2c.writeto(BH1750_ADDR, BH1750_CMD_POWER_ON)
            print('[SENSOR] BH1750 ready at 0x%02X' % BH1750_ADDR)
        except OSError:
            print('[SENSOR] BH1750 not detected')

        # PIR initial state
        self._occupancy = self.pir.value()
        print('[SENSOR] PIR on GPIO%d (initial: %s)' % (
            config.PIR_GPIO_PIN, 'OCCUPIED' if self._occupancy else 'VACANT'))

        print('[SENSOR] All sensors initialized')

    def _dht20_check_calibration(self):
        """Check DHT20 calibration bit, re-init if needed."""
        try:
            status = self.i2c.readfrom(DHT20_ADDR, 1)
            if (status[0] & 0x08) == 0:
                print('[SENSOR] DHT20: not calibrated, sending init')
                for cmd_byte in (0x1B, 0x1C, 0x1E):
                    self.i2c.writeto(DHT20_ADDR, bytes([cmd_byte, 0x00, 0x00]))
                    time.sleep_ms(10)
            else:
                print('[SENSOR] DHT20 ready at 0x%02X' % DHT20_ADDR)
        except OSError:
            print('[SENSOR] DHT20 not detected')

    def _dht20_read(self):
        """Read DHT20 → (temp_c100, humidity_c100) or (0, 0) on failure."""
        try:
            # Trigger measurement
            self.i2c.writeto(DHT20_ADDR, DHT20_CMD_TRIGGER)
            time.sleep_ms(DHT20_MEAS_DELAY)

            # Read 7 bytes: status + 5 data + CRC
            data = self.i2c.readfrom(DHT20_ADDR, 7)

            # Check busy bit
            if data[0] & 0x80:
                time.sleep_ms(40)
                data = self.i2c.readfrom(DHT20_ADDR, 7)
                if data[0] & 0x80:
                    print('[SENSOR] DHT20 still busy')
                    return 0, 0

            # Extract 20-bit raw values
            raw_hum = (data[1] << 12) | (data[2] << 4) | (data[3] >> 4)
            raw_temp = ((data[3] & 0x0F) << 16) | (data[4] << 8) | data[5]

            # Convert to x100 units
            humidity_c100 = (raw_hum * 10000) // (1 << 20)
            temp_c100 = (raw_temp * 20000) // (1 << 20) - 5000

            return temp_c100, humidity_c100

        except OSError as e:
            print('[SENSOR] DHT20 read error:', e)
            return 0, 0

    def _bh1750_read(self):
        """Read BH1750 → lux or 0 on failure."""
        try:
            # Power on + start one-time high-res measurement
            self.i2c.writeto(BH1750_ADDR, BH1750_CMD_POWER_ON)
            self.i2c.writeto(BH1750_ADDR, BH1750_CMD_HRES_1X)
            time.sleep_ms(BH1750_MEAS_DELAY)

            # Read 2 bytes (big-endian)
            data = self.i2c.readfrom(BH1750_ADDR, 2)
            raw = (data[0] << 8) | data[1]
            lux = (raw * 10) // 12  # integer approximation of raw/1.2
            return lux

        except OSError as e:
            print('[SENSOR] BH1750 read error:', e)
            return 0

    def read_env(self):
        """Read all environmental sensors → (temp_c100, humidity_c100, light_lux)."""
        temp, humidity = self._dht20_read()
        light = self._bh1750_read()
        return temp, humidity, light

    def get_occupancy(self):
        """Poll PIR GPIO directly → 0=vacant, 1=occupied."""
        self._occupancy = self.pir.value()
        return self._occupancy
