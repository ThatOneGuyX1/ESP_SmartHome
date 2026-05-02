"""
Sensor Task — moving average filter, PIR debounce, adaptive reporting, alerts.
Mirrors sensor_task.c from the C firmware.
Supports both always-on (async loop) and deep-sleep (one-shot) modes.
"""
import time
import config
import message

# ── Dynamic thresholds (settable at runtime via commands) ──────────────
temp_high_threshold = config.TEMP_HIGH_THRESHOLD
temp_low_threshold  = config.TEMP_LOW_THRESHOLD
sample_interval_ms  = config.SENSOR_SAMPLE_INTERVAL_MS
voc_threshold       = config.VOC_THRESHOLD
nox_threshold       = config.NOX_THRESHOLD


def set_temp_thresholds(high_c100, low_c100):
    global temp_high_threshold, temp_low_threshold
    temp_high_threshold = high_c100
    temp_low_threshold  = low_c100
    print('[SENSOR] Temperature thresholds updated: high=%.2f C  low=%.2f C' % (
        high_c100 / 100, low_c100 / 100))


def get_temp_thresholds():
    return temp_high_threshold, temp_low_threshold


def set_air_quality_tresholds(voc, nox):
    global voc_threshold, nox_threshold
    voc_threshold = voc
    nox_threshold = nox
    print('[SENSOR] Air quality thresholds updated: voc=%d nox=%d') % (voc, nox)


def get_air_quality_thresholds():
    return voc_threshold, nox_threshold


# ── Moving Average Filter ──────────────────────────────────────────────

class Filter:
    def __init__(self, window=config.FILTER_WINDOW_SIZE):
        self.window = window
        self.buf = [0] * window
        self.idx = 0
        self.count = 0

    def update(self, sample):
        self.buf[self.idx] = sample
        self.idx = (self.idx + 1) % self.window
        if self.count < self.window:
            self.count += 1
        return sum(self.buf[:self.count]) // self.count


# ── PIR Occupancy Debounce ─────────────────────────────────────────────

class OccupancyDebouncer:
    """Asymmetric debounce: immediate OCCUPIED, slow VACANT."""
    def __init__(self, timeout=config.VACANT_TIMEOUT_COUNT):
        self.timeout = timeout
        self.state = 0
        self.vacant_counter = 0

    def update(self, raw_occ):
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


# ── Adaptive Reporting ─────────────────────────────────────────────────

class AdaptiveReporter:
    """Track deadbands and suppress redundant transmissions."""
    def __init__(self):
        self.last_temp = -32768  # INT16_MIN
        self.last_humidity = 0
        self.last_light = 0
        self.last_voc = 0
        self.last_nox = 0
        self.silent_cycles = 0

    def should_send(self, temp, humidity, light, occ, prev_occ, voc, nox):
        # Always send if occupancy changed
        if occ != prev_occ:
            return True
        # First reading
        if self.last_temp == -32768:
            return True
        # Max silent cycles reached
        if self.silent_cycles >= config.MAX_SILENT_CYCLES:
            return True
        # Check deadbands
        if abs(temp - self.last_temp) >= config.TEMP_DEADBAND:
            return True
        if abs(humidity - self.last_humidity) >= config.HUMIDITY_DEADBAND:
            return True
        if abs( - self.last_temp) >= config.TEMP_DEADBAND:
            return True
        if abs(voc - self.last_voc) >= config.VOC_DEADBAND:
            return True
        if abs(nox - self.last_nox) >= config.NOX_DEADBAND:
            return True
        return False

    def mark_sent(self, temp, humidity, light, voc, nox):
        self.last_temp = temp
        self.last_humidity = humidity
        self.last_light = light
        self.last_voc = voc
        self.last_nox = nox
        self.silent_cycles = 0

    def mark_skipped(self):
        self.silent_cycles += 1


# ── Core read-and-send logic ──────────────────────────────────────────

def _read_and_send(hal, mesh, temp_filter, hum_filter, light_filter,
                   voc_filter, nox_filter, debouncer, reporter, state):
    """Single sensor read + process + send cycle. state is a mutable dict."""
    # Read raw sensors
    temp, humidity, light, voc, nox = hal.read_env()
    raw_occ = hal.get_occupancy()

    # Apply moving average filter
    temp = temp_filter.update(temp)
    humidity = hum_filter.update(humidity)
    light = light_filter.update(light)
    voc = voc_filter.update(voc)
    nox = nox_filter.update(nox)

    # Debounce PIR
    occupancy = debouncer.update(raw_occ)

    print('[SENSOR] Reading: temp=%.2f C humidity=%.2f%% light=%u lux VOC=%u NOX=%u occ=%s (raw=%s, n=%u)' % (
        temp / 100, humidity / 100, light, voc, nox, 
        'OCCUPIED' if occupancy else 'VACANT',
        'OCC' if raw_occ else 'VAC',
        temp_filter.count))

    # Temperature alert check
    if temp > temp_high_threshold or temp < temp_low_threshold:
        print('[SENSOR] Temperature ALERT: %.2f C' % (temp / 100))
        payload = message.pack_alert(1, abs(temp))
        mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_ALERT, payload)

    # Air quality alert check
    if voc > voc_threshold:
        print('[SENSOR] VOC ALERT: %u C' % voc)
        payload = message.pack_alert(0x20, voc)
        mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_ALERT, payload)
    if nox > nox_threshold:
        print('[SENSOR] NOX ALERT: %.2f C' % nox)
        payload = message.pack_alert(0x21, nox)
        mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_ALERT, payload)

    # Occupancy transition alert
    if not state['first'] and occupancy != state['prev_occ']:
        print('[SENSOR] Occupancy transition: %s -> %s' % (
            'OCCUPIED' if state['prev_occ'] else 'VACANT',
            'OCCUPIED' if occupancy else 'VACANT'))
        payload = message.pack_alert(0x10, occupancy)
        mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_ALERT, payload)

    prev_occ = state['prev_occ']
    state['prev_occ'] = occupancy
    state['first'] = False

    # Adaptive reporting
    if reporter.should_send(temp, humidity, light, occupancy, prev_occ, voc, nox):
        payload = message.pack_sensor_data(temp, humidity, light, occupancy, voc, nox)
        ok = mesh.send(config.GATEWAY_MAC, message.MSG_TYPE_SENSOR_DATA, payload)
        if ok:
            print('[SENSOR] SENSOR_DATA sent (changed or keepalive)')
            reporter.mark_sent(temp, humidity, light)
        else:
            print('[SENSOR] Failed to send SENSOR_DATA')
    else:
        reporter.mark_skipped()
        print('[SENSOR] Readings stable -- skipped TX (%u/%u cycles)' % (
            reporter.silent_cycles, config.MAX_SILENT_CYCLES))


# ── Always-on async loop ──────────────────────────────────────────────

async def sensor_loop(hal, mesh):
    """Async sensor loop for always-on relay mode."""
    import uasyncio as asyncio

    print('[SENSOR] Sensor task (ALWAYS-ON relay mode)')
    hal.init()

    temp_filter = Filter()
    hum_filter = Filter()
    light_filter = Filter()
    voc_filter = Filter()
    nox_filter = Filter()
    debouncer = OccupancyDebouncer()
    reporter = AdaptiveReporter()
    state = {'prev_occ': 0, 'first': True}

    while True:
        _read_and_send(hal, mesh, temp_filter, hum_filter, light_filter, voc_filter, nox_filter,
                       debouncer, reporter, state)
        await asyncio.sleep_ms(sample_interval_ms)


# ── Deep-sleep one-shot ───────────────────────────────────────────────

def deep_sleep_one_shot(hal, mesh):
    """Single read-and-send, then enter deep sleep."""
    import machine as mach
    import esp32

    print('[SENSOR] Sensor task (DEEP-SLEEP mode)')

    # Check wake reason
    reason = mach.wake_reason()
    if reason == mach.PIN_WAKE:
        print('[SENSOR] Woke from deep sleep: PIR MOTION (ext1)')
    elif reason == mach.TIMER_WAKE:
        print('[SENSOR] Woke from deep sleep: TIMER')
    else:
        print('[SENSOR] First boot (not waking from deep sleep)')

    hal.init()

    temp_filter = Filter()
    hum_filter = Filter()
    light_filter = Filter()
    voc_filter = Filter()
    nox_filter = Filter()
    debouncer = OccupancyDebouncer()
    reporter = AdaptiveReporter()
    state = {'prev_occ': 0, 'first': True}

    _read_and_send(hal, mesh, temp_filter, hum_filter, light_filter, voc_filter, nox_filter,
                   debouncer, reporter, state)

    # Give radio time to finish TX
    time.sleep_ms(200)

    # Configure wake sources
    pir_pin = mach.Pin(config.PIR_GPIO_PIN)
    esp32.wake_on_ext1([pir_pin], esp32.WAKEUP_ANY_HIGH)

    print('[SENSOR] Deep-sleep timer: %d ms' % sample_interval_ms)
    print('[SENSOR] Deep-sleep ext1 wakeup: GPIO %d (PIR motion)' % config.PIR_GPIO_PIN)
    print('[SENSOR] Entering deep sleep...')
    mach.deepsleep(sample_interval_ms)
