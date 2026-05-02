# config.py — Host Gateway Configuration

ESPNOW_CHANNEL = 1   # must match sensor nodes

# Update GATEWAY_MAC in node_a_micropython/config.py to match
# the MAC printed by this gateway on boot.

def mac_to_str(mac):
    return ':'.join('%02X' % b for b in mac)
