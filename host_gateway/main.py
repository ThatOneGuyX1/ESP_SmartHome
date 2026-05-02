# main.py — Host ESP32 Gateway
# Receives ESP-NOW frames from sensor nodes and prints one JSON
# object per line over USB serial for the PC GUI.
#
# JSON schema (matches GUI.py SerialReader expectations):
#   {
#     "type":    "sensor_data" | "health" | "alert" | "discovery",
#     "sender":  "AA:BB:CC:DD:EE:FF",
#     "message": "<human-readable summary>",
#     "trail":   [],
#     "health":  {"temp": int, "battery": int, "uptime": int}
#   }

import network
import espnow
import ujson
import time
import message
from config import ESPNOW_CHANNEL, mac_to_str

ALERT_NAMES = {
    0x01: 'TEMP_HIGH',
    0x02: 'TEMP_LOW',
    0x10: 'OCCUPANCY_ON',
    0x20: 'PERSON_DETECTED',
    0x21: 'PERSON_CLEARED',
}

NODE_TYPES = {
    0x00: 'GATEWAY',
    0x01: 'SENSOR_A',
    0x02: 'SENSOR_B',
    0x03: 'SENSOR_C',
}


def emit(msg_type, sender_mac, msg_str, health=None):
    """Print one JSON line to serial."""
    print(ujson.dumps({
        'type':    msg_type,
        'sender':  mac_to_str(sender_mac),
        'message': msg_str,
        'trail':   [],
        'health':  health or {},
    }))


# ── Frame handlers ────────────────────────────────────────────

def handle_sensor_data(src_mac, payload):
    temp_c100, hum_c100, light_lux, occupancy = message.unpack_sensor_data(payload)
    msg = 'T:%.1fC H:%.1f%% L:%dlux PIR:%d' % (
        temp_c100 / 100, hum_c100 / 100, light_lux, occupancy)
    emit('sensor_data', src_mac, msg,
         health={'temp': temp_c100 // 100, 'battery': 0, 'uptime': 0})


def handle_health(src_mac, payload):
    batt_mv, batt_soc, chip_c100, rssi, heap, uptime = message.unpack_health(payload)
    msg = 'bat=%dmV(%d%%) chip=%.1fC rssi=%ddBm heap=%d' % (
        batt_mv, batt_soc, chip_c100 / 100, rssi, heap)
    emit('health', src_mac, msg,
         health={'temp': chip_c100 // 100, 'battery': batt_soc, 'uptime': uptime // 1000})


def handle_alert(src_mac, payload):
    alert_code, sensor_reading = message.unpack_alert(payload)
    name = ALERT_NAMES.get(alert_code, 'UNKNOWN_0x%02X' % alert_code)
    emit('alert', src_mac, '%s val=%d' % (name, sensor_reading))


def handle_discovery(src_mac, payload):
    node_type, dist_level, caps = message.unpack_discovery(payload)
    type_name = NODE_TYPES.get(node_type, 'UNKNOWN')
    emit('discovery', src_mac, '%s caps=0x%02X' % (type_name, caps))


HANDLERS = {
    message.MSG_TYPE_SENSOR_DATA: handle_sensor_data,
    message.MSG_TYPE_HEALTH:      handle_health,
    message.MSG_TYPE_ALERT:       handle_alert,
    message.MSG_TYPE_DISCOVERY:   handle_discovery,
}


# ── Init ──────────────────────────────────────────────────────

def init():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.config(channel=ESPNOW_CHANNEL)
    own_mac = sta.config('mac')

    # [BOOT] prefix is intentionally skipped by the GUI's JSON parser,
    # but is useful when monitoring the raw serial port.
    print('[BOOT] Gateway MAC: ' + mac_to_str(own_mac))
    print('[BOOT] Listening on ESP-NOW channel %d' % ESPNOW_CHANNEL)

    en = espnow.ESPNow()
    en.active(True)
    return en


# ── Main loop ─────────────────────────────────────────────────

def main():
    en = init()

    while True:
        try:
            host, data = en.recv(100)
            if data is None:
                continue

            if not message.validate(data):
                print('[WARN] Bad frame (CRC/TTL fail)')
                continue

            frame = message.deserialize(data)
            if frame is None:
                continue

            handler = HANDLERS.get(frame['msg_type'])
            if handler:
                handler(frame['src_mac'], frame['payload'])
            else:
                print('[WARN] Unknown msg_type=0x%02X' % frame['msg_type'])

        except OSError as e:
            print('[ERR] ' + str(e))
            time.sleep_ms(200)


main()
