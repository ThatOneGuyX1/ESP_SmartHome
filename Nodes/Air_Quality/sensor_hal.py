"""
Sensor Hardware Abstraction Layer — Air Quality Node.
Drives SGP40 (VOC only).

IMPORTANT: The SGP40 heater must be kept on continuously for stable readings.
The datasheet specifies measuring every 1 second. Sampling slower than this
causes the hotplate to cool between reads, producing unstable baselines.
The sensor_task calls read_voc() at 1 Hz; the 5-second reporting interval
is handled by the adaptive reporter, not by slowing down the read loop.
"""
import machine
import time

# I2C address
SGP40_ADDR = 0x59

# SGP40 command codes (from datasheet)
SGP40_CMD_MEASURE_RAW     = bytes([0x26, 0x0F])
SGP40_CMD_HEATER_OFF      = bytes([0x36, 0x15])
SGP40_MEASURE_DELAY_MS    = 30   # datasheet max measurement duration

# Default compensation ticks for 25 °C / 50 %RH (datasheet default values)
_DEFAULT_RH_TICKS = 0x8000   # 50 %RH
_DEFAULT_T_TICKS  = 0x6666   # 25 °C


class SensorHAL:
    def __init__(self, i2c=None):
        self.i2c = i2c

    def init(self):
        """Scan I2C and verify SGP40 is present. No conditioning needed — just start measuring."""
        if self.i2c is None:
            raise RuntimeError('I2C bus must be provided to SensorHAL')

        devices = self.i2c.scan()
        print('[SENSOR] I2C devices:', ['0x%02X' % d for d in devices])

        if SGP40_ADDR not in devices:
            print('[SENSOR] SGP40 NOT found at 0x%02X' % SGP40_ADDR)
            return

        # Discard the first reading per datasheet recommendation
        try:
            self._measure_raw()
            print('[SENSOR] SGP40 ready at 0x%02X (first reading discarded)' % SGP40_ADDR)
        except OSError as e:
            print('[SENSOR] SGP40 init error:', e)

        print('[SENSOR] Sensors initialized')

    # ── SGP40 internals ────────────────────────────────────────────────

    def _measure_raw(self) -> int:
        """
        Send measure command with default RH/T ticks and return raw SRAW_VOC.
        Raw value is proportional to log(resistance).
        Clean air = HIGH value (~20000-30000).
        VOC present = LOWER value (resistance drops).
        """
        # Write: 2-byte command + RH word + CRC + T word + CRC
        rh_crc = self._crc8(_DEFAULT_RH_TICKS)
        t_crc  = self._crc8(_DEFAULT_T_TICKS)
        buf = bytearray([
            0x26, 0x0F,
            (_DEFAULT_RH_TICKS >> 8) & 0xFF, _DEFAULT_RH_TICKS & 0xFF, rh_crc,
            (_DEFAULT_T_TICKS  >> 8) & 0xFF, _DEFAULT_T_TICKS  & 0xFF, t_crc,
        ])
        self.i2c.writeto(SGP40_ADDR, buf)
        time.sleep_ms(SGP40_MEASURE_DELAY_MS)

        # Read: 2-byte word + 1 CRC byte
        rbuf = bytearray(3)
        self.i2c.readfrom_into(SGP40_ADDR, rbuf)
        raw = (rbuf[0] << 8) | rbuf[1]
        if self._crc8(raw) != rbuf[2]:
            raise RuntimeError('SGP40 CRC error')
        return raw

    @staticmethod
    def _crc8(word: int) -> int:
        """Sensirion CRC-8: polynomial 0x31, init 0xFF."""
        crc = 0xFF
        for byte in ((word >> 8) & 0xFF, word & 0xFF):
            crc ^= byte
            for _ in range(8):
                crc = ((crc << 1) ^ 0x31 if crc & 0x80 else crc << 1) & 0xFF
        return crc

    # ── Public API ─────────────────────────────────────────────────────

    def read_voc(self) -> tuple:
        """
        Read SGP40 and return (raw, inverted).
          raw      — SRAW_VOC direct from sensor (high = clean, low = VOC present)
          inverted — 65535 - raw (high = more pollution, for intuitive thresholding)
        Returns (0, 0) on I2C error.
        """
        try:
            raw = self._measure_raw()
            return raw, 65535 - raw
        except OSError as e:
            print('[SENSOR] SGP40 read error:', e)
            return 0, 0
