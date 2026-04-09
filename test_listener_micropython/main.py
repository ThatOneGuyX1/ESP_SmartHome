"""
ESP-NOW Test Listener (MicroPython)
Receives and parses all frame types from Node A.
Sends demo threshold commands after 30s and 90s.
"""
import network
import espnow
import time
import struct

import config
import message

print('========================================')
print('  ESP-NOW Test Listener (MicroPython)')
print('  Waiting for Node A frames...')
print('========================================')

# WiFi STA mode
sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.config(channel=config.ESPNOW_CHANNEL)

own_mac = sta.config('mac')
print()
print('  THIS LISTENER MAC:', config.mac_to_str(own_mac))
print('  Put this in Node A config.py GATEWAY_MAC')
print()

# ESP-NOW init
e = espnow.ESPNow()
e.active(True)

try:
    e.add_peer(config.NODE_A_MAC)
except OSError:
    pass
try:
    e.add_peer(config.BROADCAST_MAC)
except OSError:
    pass

print('Listening on channel %d...' % config.ESPNOW_CHANNEL)


# ── Frame parsing ─────────────────────────────────────────────────────

def parse_sensor_data(payload):
    if len(payload) < 7:
        print('  SENSOR_DATA payload too short')
        return
    temp, humidity, light, occ = message.unpack_sensor_data(payload)
    print('  SENSOR_DATA:')
    print('    Temperature : %.2f C' % (temp / 100))
    print('    Humidity    : %.2f %%RH' % (humidity / 100))
    print('    Light       : %u lux' % light)
    print('    Occupancy   : %s' % ('OCCUPIED' if occ else 'VACANT'))


def parse_health(payload):
    if len(payload) < 14:
        print('  HEALTH payload too short')
        return
    bat_mv, bat_soc, chip_temp, rssi, heap, uptime = message.unpack_health(payload)
    print('  HEALTH:')
    print('    Battery     : %u mV (%u%%)' % (bat_mv, bat_soc))
    print('    Chip temp   : %.2f C' % (chip_temp / 100))
    print('    RSSI        : %d dBm' % rssi)
    print('    Free heap   : %u bytes' % heap)
    print('    Uptime      : %u ms' % uptime)


def parse_alert(payload):
    if len(payload) < 3:
        print('  ALERT (short payload)')
        return
    code, val = message.unpack_alert(payload)
    if code == 0x10:
        print('  OCCUPANCY ALERT: %s' % ('OCCUPIED' if val else 'VACANT'))
    else:
        print('  TEMP ALERT: code=%u value=%u' % (code, val))


def parse_discovery(payload):
    if len(payload) < 3:
        print('  DISCOVERY (short payload)')
        return
    ntype, level, caps = message.unpack_discovery(payload)
    print('  DISCOVERY: node_type=0x%02X level=%u caps=0x%02X' % (ntype, level, caps))


def handle_frame(data):
    """Parse and display a received frame."""
    print('=' * 40)

    # Hex dump
    hex_str = ' '.join('%02X' % b for b in data)
    print('RAW (%d bytes): %s' % (len(data), hex_str))

    if not message.validate(data):
        print('  Invalid frame (bad CRC or TTL)')
        print('=' * 40)
        return

    frame = message.deserialize(data)
    if frame is None:
        print('  Deserialize failed')
        print('=' * 40)
        return

    print('  from=%s type=0x%02X seq=%u ttl=%u ts=%u ms len=%u' % (
        config.mac_to_str(frame['src_mac']),
        frame['msg_type'], frame['sequence_num'],
        frame['ttl'], frame['timestamp'], frame['payload_len']))

    mt = frame['msg_type']
    pl = frame['payload']
    if mt == message.MSG_TYPE_SENSOR_DATA:
        parse_sensor_data(pl)
    elif mt == message.MSG_TYPE_HEALTH:
        parse_health(pl)
    elif mt == message.MSG_TYPE_ALERT:
        parse_alert(pl)
    elif mt == message.MSG_TYPE_DISCOVERY:
        parse_discovery(pl)
    else:
        print('  (unknown type 0x%02X)' % mt)

    print('=' * 40)


# ── Command sending ───────────────────────────────────────────────────

def send_threshold_command(high_c100, low_c100):
    """Send SET_TEMP_THRESHOLDS command to Node A."""
    data = struct.pack('<hh', high_c100, low_c100) + b'\x00' * 4
    payload = message.pack_command(message.CMD_SET_TEMP_THRESHOLDS, data)

    buf = message.serialize(
        own_mac, config.NODE_A_MAC,
        message.MSG_TYPE_COMMAND,
        0, config.MESH_DEFAULT_TTL,
        config.get_uptime_ms(),
        payload
    )
    if buf is None:
        print('>>> Serialize failed')
        return

    print()
    print('>>> SENDING COMMAND: SET_TEMP_THRESHOLDS')
    print('>>>   high=%.2f C  low=%.2f C' % (high_c100 / 100, low_c100 / 100))

    try:
        ok = e.send(config.NODE_A_MAC, buf, True)
        print('>>> TX:', 'OK' if ok else 'FAIL')
    except OSError as err:
        print('>>> TX error:', err)


# ── Main loop ─────────────────────────────────────────────────────────

cmd_sent_30 = False
cmd_sent_90 = False
boot_time = time.ticks_ms()

print('Will send threshold command in 30 seconds...')

while True:
    # Non-blocking receive
    try:
        mac, data = e.recv(100)  # 100ms timeout
        if data is not None:
            handle_frame(data)
    except OSError:
        pass

    # Demo: send commands at 30s and 90s
    elapsed = time.ticks_diff(time.ticks_ms(), boot_time)
    if not cmd_sent_30 and elapsed >= 30_000:
        send_threshold_command(2800, 2000)  # 28.00 C / 20.00 C
        cmd_sent_30 = True
    if not cmd_sent_90 and elapsed >= 90_000:
        send_threshold_command(3500, 500)   # 35.00 C / 5.00 C (restore defaults)
        print('Thresholds restored to defaults')
        cmd_sent_90 = True
