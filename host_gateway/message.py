"""
Mesh Frame Protocol — serialize, deserialize, CRC-8, payload pack/unpack.
Wire-compatible with the C firmware (message.h / message.c).

Header layout (22 bytes on the wire):
  Offset  Field          Size
  0x00    src_mac        6
  0x06    dst_mac        6
  0x0C    msg_type       1
  0x0D    sequence_num   2  (little-endian)
  0x0F    ttl            1
  0x10    timestamp      4  (little-endian)
  0x14    payload_len    1
  0x15    (pad byte)     1  -- first payload byte leaked by C memcpy
  0x16    payload        N
  0x16+N  crc8           1

The packed C struct is 21 bytes; MESH_HEADER_SIZE=22 due to memcpy
copying 1 extra byte. We replicate this exactly.
"""
import struct

# Message type IDs
MSG_TYPE_SENSOR_DATA = 0x01
MSG_TYPE_ALERT       = 0x02
MSG_TYPE_HEALTH      = 0x03
MSG_TYPE_DISCOVERY   = 0x04
MSG_TYPE_HEARTBEAT   = 0x05
MSG_TYPE_COMMAND     = 0x06
MSG_TYPE_ACK         = 0x07

# Command IDs
CMD_SET_TEMP_THRESHOLDS = 0x01
CMD_SET_SAMPLE_INTERVAL = 0x02
CMD_REQUEST_READING     = 0x03

# Sizes
HEADER_SIZE     = 22
MAX_FRAME_SIZE  = 250
MAX_PAYLOAD     = MAX_FRAME_SIZE - HEADER_SIZE - 1  # 227

# struct format for the 21 real header bytes (little-endian)
_HDR_FMT = '<6s6sBHBIB'
_HDR_PACK_SIZE = 21  # struct.calcsize(_HDR_FMT)

# Payload struct formats
_SENSOR_FMT    = '<hHHB'     # 7 bytes
_HEALTH_FMT    = '<HBhbII'   # 14 bytes
_ALERT_FMT     = '<BH'       # 3 bytes
_DISCOVERY_FMT = '<BBB'      # 3 bytes
_COMMAND_FMT   = '<B8s'      # 9 bytes


def crc8_compute(data):
    """CRC-8 with polynomial 0x07 (CRC-8-CCITT), init=0x00.
    Byte-identical to the C implementation."""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def serialize(src_mac, dst_mac, msg_type, seq, ttl, timestamp, payload):
    """Serialize a frame to bytes for ESP-NOW transmission.
    Returns the complete frame bytes including CRC, or None on error."""
    payload_len = len(payload)
    if payload_len > MAX_PAYLOAD:
        return None

    # Pack 21-byte header
    hdr = struct.pack(_HDR_FMT,
                      src_mac, dst_mac, msg_type, seq, ttl,
                      timestamp, payload_len)

    # Pad byte = first payload byte (matches C memcpy overflow behavior)
    pad = payload[0:1] if payload else b'\x00'

    frame = hdr + pad + payload
    crc = crc8_compute(frame)
    return frame + bytes([crc])


def deserialize(buf):
    """Deserialize raw bytes into a frame dict.
    Returns dict with header fields + 'payload' bytes + 'crc8', or None."""
    if len(buf) < HEADER_SIZE + 1:
        return None

    # Unpack 21 real header bytes
    (src_mac, dst_mac, msg_type, seq, ttl,
     timestamp, payload_len) = struct.unpack_from(_HDR_FMT, buf, 0)

    if payload_len > MAX_PAYLOAD:
        return None

    expected_len = HEADER_SIZE + payload_len + 1
    if len(buf) < expected_len:
        return None

    # Validate CRC (over header + payload, excluding CRC byte)
    crc_offset = HEADER_SIZE + payload_len
    computed = crc8_compute(buf[:crc_offset])
    if buf[crc_offset] != computed:
        return None

    # Validate TTL
    if ttl == 0:
        return None

    payload = buf[HEADER_SIZE:HEADER_SIZE + payload_len]

    return {
        'src_mac':      src_mac,
        'dst_mac':      dst_mac,
        'msg_type':     msg_type,
        'sequence_num': seq,
        'ttl':          ttl,
        'timestamp':    timestamp,
        'payload_len':  payload_len,
        'payload':      payload,
        'crc8':         buf[crc_offset],
    }


def validate(buf):
    """Quick validation: length, payload_len bounds, TTL, CRC."""
    if len(buf) < HEADER_SIZE + 1:
        return False
    payload_len = buf[20]  # offset of payload_len in header
    if payload_len > MAX_PAYLOAD:
        return False
    expected_len = HEADER_SIZE + payload_len + 1
    if len(buf) < expected_len:
        return False
    ttl = buf[15]  # offset of ttl in header
    if ttl == 0:
        return False
    crc_offset = HEADER_SIZE + payload_len
    return buf[crc_offset] == crc8_compute(buf[:crc_offset])


# ── Payload pack/unpack ───────────────────────────────────────────────

def pack_sensor_data(temp_c100, humidity_c100, light_lux, occupancy):
    """Pack sensor data payload (7 bytes)."""
    return struct.pack(_SENSOR_FMT, temp_c100, humidity_c100, light_lux, occupancy)


def unpack_sensor_data(payload):
    """Unpack sensor data → (temp_c100, humidity_c100, light_lux, occupancy)."""
    return struct.unpack(_SENSOR_FMT, payload[:7])


def pack_health(battery_mv, battery_soc, chip_temp_c100, rssi_dbm, heap_free, uptime_ms):
    """Pack health payload (14 bytes)."""
    return struct.pack(_HEALTH_FMT,
                       battery_mv, battery_soc, chip_temp_c100,
                       rssi_dbm, heap_free, uptime_ms)


def unpack_health(payload):
    """Unpack health → (battery_mv, soc, chip_temp, rssi, heap, uptime)."""
    return struct.unpack(_HEALTH_FMT, payload[:14])


def pack_alert(alert_code, sensor_reading):
    """Pack alert payload (3 bytes)."""
    return struct.pack(_ALERT_FMT, alert_code, sensor_reading)


def unpack_alert(payload):
    """Unpack alert → (alert_code, sensor_reading)."""
    return struct.unpack(_ALERT_FMT, payload[:3])


def pack_discovery(node_type, distance_level, capabilities):
    """Pack discovery payload (3 bytes)."""
    return struct.pack(_DISCOVERY_FMT, node_type, distance_level, capabilities)


def unpack_discovery(payload):
    """Unpack discovery → (node_type, distance_level, capabilities)."""
    return struct.unpack(_DISCOVERY_FMT, payload[:3])


def pack_command(command_id, data=b''):
    """Pack command payload (9 bytes). data is padded/truncated to 8 bytes."""
    padded = (data + b'\x00' * 8)[:8]
    return struct.pack(_COMMAND_FMT, command_id, padded)


def unpack_command(payload):
    """Unpack command → (command_id, data_bytes)."""
    cmd_id, data = struct.unpack(_COMMAND_FMT, payload[:9])
    return cmd_id, data
