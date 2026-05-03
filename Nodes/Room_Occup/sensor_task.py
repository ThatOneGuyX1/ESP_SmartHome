"""
Sensor Task — moving average filter, PIR debounce, adaptive reporting, alerts.
ECE 568 Smart Home Mesh Network (MicroPython + smart_esp_comm)

Packet routing:
  - Sensor data and alerts are sent as ACT_REPORT_HOME packets so relay
    nodes forward them hop-by-hop toward the home gateway.
  - The 32-byte message field carries a compact struct payload.

Sensor data payload (7 bytes):
  Bytes 0-1 : temp_c100     (int16,  °C × 100, little-endian)
  Bytes 2-3 : humidity_c100 (uint16, %RH × 100, little-endian)
  Bytes 4-5 : light_lux     (uint16, lux, little-endian)
  Byte  6   : occupancy     (uint8,  0=vacant 1=occupied)

Alert payload (3 bytes):
  Byte  0   : alert_code    (uint8)
  Bytes 1-2 : sensor_value  (uint16, little-endian)

Alert codes:
  0x01 : Temperature out of range
  0x10 : Occupancy state change
"""
import struct
import uasyncio as asyncio

import config
import smart_esp_comm as comm

# ── Payload formats ───────────────────────────────────────────────────
_SENSOR_FMT = '<hHHB'   # temp, humidity, light, occupancy  (7 bytes)
_ALERT_FMT  = '<BH'     # alert_code, sensor_value           (3 bytes)

# ── Dynamic thresholds (adjustable at runtime via command packets) ─────
temp_high_threshold = config.TEMP_HIGH_THRESHOLD
temp_low_threshold  = config.TEMP_LOW_THRESHOLD
sample_interval_ms  = config.SENSOR_SAMPLE_INTERVAL_MS


def set_temp_thresholds(high_c100: int, low_c100: int):
    """Update temperature alert thresholds at runtime."""
    global temp_high_threshold, temp_low_threshold
    temp_high_threshold = high_c100
    temp_low_threshold  = low_c100
    print('[SENSOR] Thresholds updated: high=%.2f C  low=%.2f C' % (
        high_c100 / 100, low_c100 / 100))


def get_temp_thresholds():
    return temp_high_threshold, temp_low_threshold


# ── Moving Average Filter ─────────────────────────────────────────────

class Filter:
    """Simple fixed-window moving average."""
    def __init__(self, window=config.FILTER_WINDOW_SIZE):
        self.window = window
        self.buf    = [0] * window
        self.idx    = 0
        self.count  = 0

    def update(self, sample: int) -> int:
        self.buf[self.idx] = sample
        self.idx = (self.idx + 1) % self.window
        if self.count < self.window:
            self.count += 1
        return sum(self.buf[:self.count]) // self.count


# ── PIR Occupancy Debounce ────────────────────────────────────────────

class OccupancyDebouncer:
    """
    Asymmetric debounce for PIR sensor:
      - OCCUPIED triggers immediately on any active reading.
      - VACANT requires `timeout` consecutive inactive readings.
    """
    def __init__(self, timeout=config.VACANT_TIMEOUT_COUNT):
        self.timeout       = timeout
        self.state         = 0
        self.vacant_counter = 0

    def update(self, raw_occ: int) -> int:
        if raw_occ:
            self.vacant_counter = 0
            if not self.state:
                self.state = 1
                print('[SENSOR] PIR: motion detected -> OCCUPIED')
        else:
            self.vacant_counter += 1
            if self.state and self.vacant_counter >= self.timeout:
                self.state = 0
                print('[SENSOR] PIR: no motion for %d reads -> VACANT' % self.timeout)
        return self.state


# ── Adaptive Reporting ────────────────────────────────────────────────

class AdaptiveReporter:
    """
    Suppress redundant transmissions using per-channel deadbands.
    Forces a send after MAX_SILENT_CYCLES regardless of change.
    """
    def __init__(self):
        self.last_temp     = -32768   # sentinel: force first send
        self.last_humidity = 0
        self.last_light    = 0
        self.silent_cycles = 0

    def should_send(self, temp, humidity, light, occ, prev_occ) -> bool:
        if occ != prev_occ:                                         return True
        if self.last_temp == -32768:                                return True
        if self.silent_cycles >= config.MAX_SILENT_CYCLES:         return True
        if abs(temp     - self.last_temp)     >= config.TEMP_DEADBAND:     return True
        if abs(humidity - self.last_humidity) >= config.HUMIDITY_DEADBAND: return True
        if abs(light    - self.last_light)    >= config.LIGHT_DEADBAND:    return True
        return False

    def mark_sent(self, temp, humidity, light):
        self.last_temp     = temp
        self.last_humidity = humidity
        self.last_light    = light
        self.silent_cycles = 0

    def mark_skipped(self):
        self.silent_cycles += 1


# ── Internal send helpers ─────────────────────────────────────────────

def _send_toward_home(payload: bytes):
    """
    Route a payload toward the home node using ACT_REPORT_HOME.
    Finds the best next hop via smart_esp_comm's routing table.
    Drops the packet with a warning if no route exists.
    """
    next_hop = comm._find_next_hop_toward_home()
    if next_hop is None:
        print('[SENSOR] No route toward home -- packet dropped.')
        return False

    pkt = comm.create_msg_packet(
        dest_mac = next_hop,
        action   = comm.ACT_REPORT_HOME,
        message  = payload,
    )
    comm.espnow_send(next_hop, pkt)
    return True


# ── Core read-and-send cycle ──────────────────────────────────────────

def _read_and_send(hal, temp_filter, hum_filter, light_filter,
                   debouncer, reporter, state):
    """
    Single sensor read → filter → debounce → alert check → adaptive send.
    `state` is a mutable dict: {'prev_occ': int, 'first': bool}
    """
    # Raw reads
    temp, humidity, light = hal.read_env()
    raw_occ = hal.get_occupancy()

    # Filter
    temp     = temp_filter.update(temp)
    humidity = hum_filter.update(humidity)
    light    = light_filter.update(light)

    # Debounce PIR
    occupancy = debouncer.update(raw_occ)

    print('[SENSOR] temp=%.2f C  hum=%.2f%%  light=%u lux  occ=%s  (raw=%s  n=%u)' % (
        temp / 100, humidity / 100, light,
        'OCC' if occupancy else 'VAC',
        'OCC' if raw_occ   else 'VAC',
        temp_filter.count))

    # ── Temperature alert ─────────────────────────────────────────
    if temp > temp_high_threshold or temp < temp_low_threshold:
        print('[SENSOR] Temp ALERT: %.2f C' % (temp / 100))
        alert_payload = struct.pack(_ALERT_FMT, 0x01, abs(temp) & 0xFFFF)
        _send_toward_home(alert_payload)

    # ── Occupancy transition alert ────────────────────────────────
    if not state['first'] and occupancy != state['prev_occ']:
        print('[SENSOR] Occupancy: %s -> %s' % (
            'OCC' if state['prev_occ'] else 'VAC',
            'OCC' if occupancy         else 'VAC'))
        alert_payload = struct.pack(_ALERT_FMT, 0x10, occupancy)
        _send_toward_home(alert_payload)

    prev_occ          = state['prev_occ']
    state['prev_occ'] = occupancy
    state['first']    = False

    # ── Adaptive sensor data report ───────────────────────────────
    if reporter.should_send(temp, humidity, light, occupancy, prev_occ):
        sensor_payload = struct.pack(_SENSOR_FMT, temp, humidity, light, occupancy)
        ok = _send_toward_home(sensor_payload)
        if ok:
            print('[SENSOR] SENSOR_DATA sent.')
            reporter.mark_sent(temp, humidity, light)
        else:
            print('[SENSOR] SENSOR_DATA send failed.')
    else:
        reporter.mark_skipped()
        print('[SENSOR] Stable -- TX skipped (%u/%u silent cycles).' % (
            reporter.silent_cycles, config.MAX_SILENT_CYCLES))


# ── Always-on async loop ──────────────────────────────────────────────

async def sensor_loop(hal):
    """
    Async sensor loop for always-on mode.

    Args:
        hal : initialized SensorHAL instance
    """
    print('[SENSOR] Sensor task started (always-on mode).')
    hal.init()

    temp_filter  = Filter()
    hum_filter   = Filter()
    light_filter = Filter()
    debouncer    = OccupancyDebouncer()
    reporter     = AdaptiveReporter()
    state        = {'prev_occ': 0, 'first': True}

    while True:
        _read_and_send(hal, temp_filter, hum_filter, light_filter,
                       debouncer, reporter, state)
        await asyncio.sleep_ms(sample_interval_ms)
