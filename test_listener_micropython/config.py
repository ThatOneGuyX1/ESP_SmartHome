"""
Test Listener Configuration — shared constants.
"""
import time

ESPNOW_CHANNEL = 1

BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
NODE_A_MAC    = b'\x00\x4b\x12\xbe\xce\xd4'

MESH_HEADER_SIZE = 22
MESH_DEFAULT_TTL = 5


def mac_to_str(mac):
    return ':'.join('%02X' % b for b in mac)


def get_uptime_ms():
    return time.ticks_ms() & 0xFFFFFFFF
