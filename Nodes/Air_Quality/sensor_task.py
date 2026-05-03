"""
Sensor Task — Air Quality Node (SGP40: VOC only).
Uses smart_esp_comm for all ESP-NOW communication.

Reads at 1 Hz to keep the SGP40 heater on continuously (per datasheet).
Reporting to the gateway is throttled separately by the adaptive reporter.
"""
import struct
import time

# ── Thresholds and timing ──────────────────────────────────────────────
# VOC_THRESHOLD applies to the INVERTED value (65535 - raw).
# In clean air the inverted value sits around 35000-45000.
# VOC events push raw DOWN, so inverted goes UP — set threshold above baseline.
# Leave at 0 to disable alerts until you've observed your clean-air baseline.
VOC_ALERT_THRESHOLD = 0        # set after observing your baseline (0 = disabled)
VOC_DEADBAND        = 300      # minimum change in inverted value before reporting
MAX_SILENT_CYCLES   = 5        # force a TX every N seconds when stable
FILTER_WINDOW_SIZE  = 5        # moving average over last N 1-second samples

READ_INTERVAL_MS    = 1_000    # 1 Hz — keep heater on per datasheet
REPORT_INTERVAL_S   = 5        # send data to gateway every ~5 reads


def set_voc_alert_threshold(threshold):
    global VOC_ALERT_THRESHOLD
    VOC_ALERT_THRESHOLD = threshold
    print('[SENSOR] VOC alert threshold set to %d' % threshold)


# ── Moving Average Filter ──────────────────────────────────────────────

class Filter:
    def __init__(self, window=FILTER_WINDOW_SIZE):
        self.window = window
        self.buf    = [0] * window
        self.idx    = 0
        self.count  = 0

    def update(self, sample):
        self.buf[self.idx] = sample
        self.idx = (self.idx + 1) % self.window
        if self.count < self.window:
            self.count += 1
        return sum(self.buf[:self.count]) // self.count


# ── Adaptive Reporter ──────────────────────────────────────────────────

class AdaptiveReporter:
    def __init__(self):
        self.last_inverted = -1
        self.silent_cycles = 0

    def should_send(self, inverted):
        if self.last_inverted == -1:
            return True
        if self.silent_cycles >= MAX_SILENT_CYCLES:
            return True
        if abs(inverted - self.last_inverted) >= VOC_DEADBAND:
            return True
        return False

    def mark_sent(self, inverted):
        self.last_inverted = inverted
        self.silent_cycles = 0

    def mark_skipped(self):
        self.silent_cycles += 1


# ── Packet payload ─────────────────────────────────────────────────────

def _pack_voc(raw, inverted) -> bytes:
    """Pack both raw and inverted as 2x uint16 little-endian (4 bytes total)."""
    return struct.pack('<HH', raw, inverted)


# ── Next hop helper ────────────────────────────────────────────────────

def _next_hop(comm):
    best_name = None
    best_hop  = comm.LOCAL_HOP
    for name in comm._get_my_neighbors():
        if name not in comm.PEER_DICT:
            continue
        if comm.PEER_DICT[name]["hop"] < best_hop:
            best_hop  = comm.PEER_DICT[name]["hop"]
            best_name = name
    if best_name is None:
        return None
    return comm.mac_bytes(comm.PEER_DICT[best_name]["mac"])


# ── Always-on async loop ──────────────────────────────────────────────

async def sensor_loop(hal, comm):
    import uasyncio as asyncio
    print('[SENSOR] SGP40 task started — reading at 1 Hz, reporting every ~%ds' % REPORT_INTERVAL_S)
    hal.init()

    raw_filter      = Filter()
    inverted_filter = Filter()
    reporter        = AdaptiveReporter()
    read_count      = 0

    while True:
        raw, inverted = hal.read_voc()
        raw_f      = raw_filter.update(raw)
        inverted_f = inverted_filter.update(inverted)
        read_count += 1

        # Log every read so you can watch the sensor react in real time
        print('[SENSOR] raw=%u  inverted=%u  (n=%u)' % (raw_f, inverted_f, raw_filter.count))

        # Only attempt TX every REPORT_INTERVAL_S seconds
        if read_count % REPORT_INTERVAL_S == 0:
            gateway_mac = _next_hop(comm)
            if gateway_mac is None:
                print('[SENSOR] No route to home -- skipping TX.')
            else:
                # Alert check (only if threshold is set)
                if VOC_ALERT_THRESHOLD > 0 and inverted_f > VOC_ALERT_THRESHOLD:
                    print('[SENSOR] VOC ALERT: inverted=%u (threshold=%u)' % (
                        inverted_f, VOC_ALERT_THRESHOLD))
                    alert_pkt = comm.create_msg_packet(
                        dest_mac = gateway_mac,
                        action   = comm.ACT_REPORT_HOME,
                        message  = b'ALERT:VOC:' + str(inverted_f).encode(),
                    )
                    comm.espnow_send(gateway_mac, alert_pkt)

                # Adaptive periodic report
                if reporter.should_send(inverted_f):
                    pkt = comm.create_msg_packet(
                        dest_mac = gateway_mac,
                        action   = comm.ACT_REPORT_HOME,
                        message  = _pack_voc(raw_f, inverted_f),
                    )
                    comm.espnow_send(gateway_mac, pkt)
                    print('[SENSOR] SENSOR_DATA sent (raw=%u inverted=%u)' % (raw_f, inverted_f))
                    reporter.mark_sent(inverted_f)
                else:
                    reporter.mark_skipped()
                    print('[SENSOR] Stable -- TX skipped (%u/%u)' % (
                        reporter.silent_cycles, MAX_SILENT_CYCLES))

        await asyncio.sleep_ms(READ_INTERVAL_MS)


# ── Deep-sleep one-shot ───────────────────────────────────────────────

def deep_sleep_one_shot(hal, comm):
    import machine as mach
    print('[SENSOR] SGP40 task (DEEP-SLEEP mode)')

    reason = mach.wake_reason()
    if reason == mach.TIMER_WAKE:
        print('[SENSOR] Woke from deep sleep: TIMER')
    else:
        print('[SENSOR] First boot')

    hal.init()
    raw, inverted = hal.read_voc()
    print('[SENSOR] raw=%u  inverted=%u' % (raw, inverted))

    gateway_mac = _next_hop(comm)
    if gateway_mac:
        pkt = comm.create_msg_packet(
            dest_mac = gateway_mac,
            action   = comm.ACT_REPORT_HOME,
            message  = _pack_voc(raw, inverted),
        )
        comm.espnow_send(gateway_mac, pkt)
        print('[SENSOR] SENSOR_DATA sent')

    time.sleep_ms(200)
    print('[SENSOR] Entering deep sleep (5000 ms)...')
    mach.deepsleep(5000)
