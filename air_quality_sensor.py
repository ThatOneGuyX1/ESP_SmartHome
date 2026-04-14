from machine import Pin, I2C
from time import sleep_ms

# Adapted from https://github.com/adafruit/Adafruit_CircuitPython_SGP41/blob/main/adafruit_sgp41.py

SDA_PIN_NO = 22
SCL_PIN_NO = 14
NEOPIXEL_PWR_PIN_NO = 2 # Just in case
neopixel_power_pin = Pin(NEOPIXEL_PWR_PIN_NO, Pin.OUT)
neopixel_power_pin.value(1)

_SGP41_DEFAULT_ADDR = 0x59
_SGP41_GENERAL_CALL_ADDR = 0x00

_SGP41_CMD_EXECUTE_CONDITIONING = 0x2612
_SGP41_CMD_MEASURE_RAW_SIGNALS = 0x2619
_SGP41_CMD_EXECUTE_SELF_TEST = 0x280E
_SGP41_CMD_TURN_HEATER_OFF = 0x3615
_SGP41_CMD_GET_SERIAL_NUMBER = 0x3682
_SGP41_CMD_SOFT_RESET = 0x0006

_SGP41_CONDITIONING_DELAY_MS = 50  # 50ms
_SGP41_MEASUREMENT_DELAY_MS = 50  # 50ms
_SGP41_SELF_TEST_DELAY_MS = 320  # 320ms

_SGP41_SELF_TEST_OK = 0xD400

class SGP41:
    """Driver for the SGP41 gas sensor."""

    def __init__(self, i2c) -> None:
        """
        Initialize the SGP41 sensor.

        :param i2c_bus: The I2C bus the SGP41 is connected to
        """

        self.i2c = i2c
        self._humidity = 50.0
        self._temperature = 25.0
        self.reset()

        # Verify device is present and working
        serial = self.serial_number
        if serial in {(0x0000, 0x0000, 0x0000), (0xFFFF, 0xFFFF, 0xFFFF)}:
            raise RuntimeError("Failed to find SGP41 sensor - check your wiring!")

    @property
    def serial_number(self):
        """
        The 48-bit serial number as a tuple of three 16-bit words.

        :return: Tuple of (word0, word1, word2)
        """
        self._write_command(_SGP41_CMD_GET_SERIAL_NUMBER)
        sleep_ms(1)  # 1ms delay
        return tuple(self._read_words(3))

    @property
    def self_test_result(self) -> int:
        """
        Execute the built-in self-test and return the raw result.

        :return: Raw 16-bit test result (0xD400 = pass)
        """
        self._write_command(_SGP41_CMD_EXECUTE_SELF_TEST)
        sleep_ms(_SGP41_SELF_TEST_DELAY_MS)
        return self._read_words(1)[0]

    @property
    def self_test_passed(self) -> bool:
        """
        Execute self-test and return True if passed, False otherwise.

        :return: True if self-test passed
        """
        result = self.self_test_result
        return result == _SGP41_SELF_TEST_OK

    def measure_raw(
        self,
        humidity: float = None,
        temperature: float = None,
    ):
        """
        Measure raw VOC and NOx signals from the sensor.

        :param humidity: Relative humidity in percent (0-100). If None, uses stored value.
        :param temperature: Temperature in degrees Celsius (-45 to 130). If None, uses stored value.
        :return: Tuple of (voc_raw, nox_raw) tick values
        """
        if humidity is None:
            humidity = self._humidity
        if temperature is None:
            temperature = self._temperature

        rh_ticks = self._humidity_to_ticks(humidity)
        t_ticks = self._temperature_to_ticks(temperature)

        self._write_command(_SGP41_CMD_MEASURE_RAW_SIGNALS, [rh_ticks, t_ticks])
        sleep_ms(_SGP41_MEASUREMENT_DELAY_MS)

        results = self._read_words(2)
        return results[0], results[1]

    def conditioning(
        self,
        humidity: float = None,
        temperature: float = None,
    ) -> int:
        """
        Execute the conditioning command for the sensor.

        The SGP41 sensor requires a conditioning period when first powered on.
        This should be called once per second for the first 10 seconds after power-up.

        :param humidity: Relative humidity in percent (0-100). If None, uses stored value.
        :param temperature: Temperature in degrees Celsius (-45 to 130). If None, uses stored value.
        :return: VOC raw tick value
        """
        if humidity is None:
            humidity = self._humidity
        if temperature is None:
            temperature = self._temperature

        rh_ticks = self._humidity_to_ticks(humidity)
        t_ticks = self._temperature_to_ticks(temperature)

        self._write_command(_SGP41_CMD_EXECUTE_CONDITIONING, [rh_ticks, t_ticks])
        sleep_ms(_SGP41_CONDITIONING_DELAY_MS)

        return self._read_words(1)[0]

    @property
    def raw_voc(self) -> int:
        """
        The raw VOC signal from the sensor using stored compensation values.

        :return: VOC raw tick value
        """
        voc_raw, _ = self.measure_raw()
        return voc_raw

    @property
    def raw_nox(self) -> int:
        """
        The raw NOx signal from the sensor using stored compensation values.

        :return: NOx raw tick value
        """
        _, nox_raw = self.measure_raw()
        return nox_raw

    def heater_off(self) -> None:
        """
        Turn off the integrated heater and enter idle mode.

        Note: The sensor will need conditioning again after turning the heater back on.
        """
        self._write_command(_SGP41_CMD_TURN_HEATER_OFF)
        sleep_ms(1)

    def reset(self) -> None:
        """
        Perform a soft reset.
        """
        buffer = bytearray(2)
        buffer[0] = (_SGP41_CMD_SOFT_RESET >> 8) & 0xFF
        buffer[1] = _SGP41_CMD_SOFT_RESET & 0xFF
        self.i2c.writeto(_SGP41_GENERAL_CALL_ADDR, buffer)

        sleep_ms(20)  # 20ms delay for device to recover

    @property
    def relative_humidity(self) -> float:
        """
        The relative humidity value used for compensation.

        :return: Relative humidity in percent (0-100)
        """
        return self._humidity

    @relative_humidity.setter
    def relative_humidity(self, value: float) -> None:
        """
        Set the relative humidity value for compensation.

        :param value: Relative humidity in percent (0-100)
        """
        self._humidity = max(0.0, min(100.0, value))

    @property
    def temperature(self) -> float:
        """
        The temperature value used for compensation.

        :return: Temperature in degrees Celsius
        """
        return self._temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        """
        Set the temperature value for compensation.

        :param value: Temperature in degrees Celsius (-45 to 130)
        """
        self._temperature = max(-45.0, min(130.0, value))

    @staticmethod
    def _humidity_to_ticks(humidity: float) -> int:
        humidity = max(0.0, min(100.0, humidity))
        return int(humidity * 65535.0 / 100.0 + 0.5)

    @staticmethod
    def _temperature_to_ticks(temperature: float) -> int:
        temperature = max(-45.0, min(130.0, temperature))
        return int((temperature + 45.0) * 65535.0 / 175.0 + 0.5)

    def _write_command(self, command: int, data = None) -> None:
        buffer = bytearray(2)
        buffer[0] = (command >> 8) & 0xFF
        buffer[1] = command & 0xFF

        if data:
            for word in data:
                buffer.append((word >> 8) & 0xFF)
                buffer.append(word & 0xFF)
                buffer.append(self._crc8(word))
        self.i2c.writeto(_SGP41_DEFAULT_ADDR, buffer)

    def _read_words(self, num_words: int):
        """
        Read data words from the sensor with CRC verification.

        :param num_words: Number of 16-bit words to read
        :return: List of data words
        :raises RuntimeError: If CRC check fails
        """
        if num_words == 0:
            return []

        buffer = bytearray(num_words * 3)  # Each word is 2 bytes + 1 CRC byte

        self.i2c.readfrom_into(_SGP41_DEFAULT_ADDR, buffer)

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
        """
        Calculate CRC-8 checksum for a 16-bit word.

        :param word: 16-bit data word
        :return: 8-bit CRC checksum
        """
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

sda_pin = Pin(SDA_PIN_NO, mode=Pin.IN, pull=Pin.PULL_UP)
if not sda_pin.value():
    # Bitbang out a reset
    scl_pin = Pin(SCL_PIN_NO, mode=Pin.OUT, value=1)
    for i in range(9):
        sleep_ms(1)
        scl_pin.value(0)
        sleep_ms(1)
        scl_pin.value(1)
    sleep_ms(1)
    if not sda_pin.value():
        print("Reset not successful")
    # Now it should be ready for input
    sda_pin.init(mode=Pin.OUT, value=0)
    sleep_ms(1)
    scl_pin.value(1)
    sleep_ms(1)
    sda_pin.value(1)
    sleep_ms(1)
    # Now it should be ready for input
    sda_pin.init(mode=Pin.IN, pull=Pin.PULL_UP)
    scl_pin.init(mode=Pin.IN, pull=Pin.PULL_UP)
else:
    scl_pin = Pin(SCL_PIN_NO, mode=Pin.IN, pull=Pin.PULL_UP)

i2c_dev = I2C(scl=scl_pin, sda=sda_pin, freq=100000, timeout=100000)
sgp41 = SGP41(i2c_dev)