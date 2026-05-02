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
SGP41_ADDR = 0x59

# DHT20 commands
DHT20_CMD_TRIGGER = bytes([0xAC, 0x33, 0x00])
DHT20_MEAS_DELAY  = 80   # ms

# BH1750 commands
BH1750_CMD_POWER_ON = bytes([0x01])
BH1750_CMD_HRES_1X  = bytes([0x20])
BH1750_MEAS_DELAY   = 180  # ms

# SGP41 commands
SGP41_CMD_EXECUTE_CONDITIONING = bytes([0x26, 0x12])
SGP41_CMD_MEASURE_RAW_SIGNALS = bytes([0x26, 0x19])
SGP41_CMD_TURN_HEATER_OFF = bytes([0x36, 0x15])
SGP41_DELAY_MS = 50  # 50ms

class SensorHAL:
    def __init__(self, i2c=None, pir_pin=None):
        self.i2c = i2c
        self.pir = machine.Pin(
            pir_pin or config.PIR_GPIO_PIN,
            machine.Pin.IN,
            machine.Pin.PULL_DOWN
        )
        self._occupancy = 0
        self._temp = 25
        self._humidity = 50

    def init(self):
        """Initialize I2C bus if not provided, check DHT20 calibration, power on BH1750."""
        # Feather ESP32 V2: GPIO2 gates power to the STEMMA QT port.
        # Must be driven HIGH before I2C devices will respond.
        stemma_pwr = machine.Pin(2, machine.Pin.OUT)
        stemma_pwr.value(1)
        time.sleep_ms(10)

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
        
        # SGP41 conditioning
        try:
            self._sgp41_conditioning()
        except OSError:
            print('[SENSOR] SGP41 not detected')

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

            # Feed to air quality sensor, if available
            self.sgp41_set_temp_humidity(humidity_c100, temp_c100)

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
        
    def _sgp41_read(self):
        try:
            rh_ticks, t_ticks = self._sgp41_humidity_temperature_to_ticks(self._humidity, self._temp)
            self._sgp41_write_command(SGP41_CMD_MEASURE_RAW_SIGNALS, [rh_ticks, t_ticks])
            time.sleep_ms(SGP41_DELAY_MS)
            results = self._sgp41_read_words(2)
            return 65535 - results[0], results[1]
        except OSError as e:
            print('[SENSOR] SGP41 read error:', e)
            return 0, 0
    
    def _sgp41_set_temp_humidity(self, humidity, temp):
        self._humidity =  max(0.0, min(100.0, humidity))
        self._temp = max(-45.0, min(130.0, temp))

    def _sgp41_conditioning(self):
        rh_ticks, t_ticks = self._sgp41_humidity_temperature_to_ticks(self._humidity, self._temp)
        self._sgp41_write_command(SGP41_CMD_EXECUTE_CONDITIONING, [rh_ticks, t_ticks])
        time.sleep_ms(SGP41_DELAY_MS)
        return self._sgp41_read_words(1)[0]

    @staticmethod
    def _sgp41_humidity_temperature_to_ticks(humidity: float, temperature: float):
        humidity = max(0.0, min(100.0, humidity))
        temperature = max(-45.0, min(130.0, temperature))
        return int(humidity * 65535.0 / 100.0 + 0.5), int((temperature + 45.0) * 65535.0 / 175.0 + 0.5)

    def _sgp41_write_command(self, command: bytearray, data = None) -> None:
        buffer = bytearray()
        buffer.extend(command)
        if data:
            for word in data:
                buffer.append((word >> 8) & 0xFF)
                buffer.append(word & 0xFF)
                buffer.append(self._crc8(word))
        self.i2c.writeto(SGP41_ADDR, buffer)

    def _sgp41_read_words(self, num_words: int):
        if num_words == 0:
            return []

        buffer = bytearray(num_words * 3)  # Each word is 2 bytes + 1 CRC byte
        self.i2c.readfrom_into(SGP41_ADDR, buffer)
        words = []
        for i in range(num_words):
            offset = i * 3
            word = (buffer[offset] << 8) | buffer[offset + 1]
            crc = buffer[offset + 2]

            if self._crc8(word) != crc:
                raise RuntimeError("CRC check failed while reading from SGP41")
            words.append(word)

        return words

    @staticmethod
    def _crc8(word: int) -> int:
        crc = 0xFF
        bytes_to_check = [(word >> 8) & 0xFF, word & 0xFF]

        for byte in bytes_to_check:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc <<= 1
                crc &= 0xFF  # Keep it 8-bit

        return crc

    def read_env(self):
        """Read all environmental sensors → (temp_c100, humidity_c100, light_lux)."""
        temp, humidity = self._dht20_read()
        light = self._bh1750_read()
        voc, nox = self._sgp41_read()
        return temp, humidity, light, voc, nox

    def get_occupancy(self):
        """Poll PIR GPIO directly → 0=vacant, 1=occupied."""
        self._occupancy = self.pir.value()
        return self._occupancy
