import network

import espnow

import json

PEER_FILE = "peer_file.json"
PEER_DICT = {}



espnow_instance = None
mac_local = None

'''
Action Items    Bit Pattern Bit Hex     Action     
Test Comm       0bxxxx xx1x 0x02        Nothing, just sends a test packet              
Report Home     0b11xx xxxx 0xC0        Message will aslo need to be forwards to home, work down the map
Add Peer        obxx11 xxxx 0x30        A peer needs to be added to network
Report Sensor   0bxxxx xxx1 0x01        A sensor is reporting its value to either the home or straight to another sesnor
Request Action  0bxxxx 1xxx 0x08        An action is being requested 
Report Action   0bxxxx 11xx 0x0C        An action that has been taken is being reported

Health Report
Byte 1: Temp
Byte 2: Battery Pecentage
Byte 3 - 6: Live time?
Byte 10:
'''


def create_msg_packet(dest,send,message,health,list_node =[], act = 0xC0): #Our baseline action is reporting to home
    '''
    The message packet is designed to provide a custom format for out esp messages. One format can also accomplish many things in on packet
    We first include the start and end points of the message (Destaionation and Sender) (12 Bytes total)
    We then include as 32 Byte message
    Action item is saying what the message is supoosed to do
    We can also send a health update on top of this. Messages between sensors do not need to do anything with this info
    We can then hold a list of 32 other Nodes that we have passed trough.
    ''' 
    # Total length is 250 Byters
    destination = None  # 06 Bytes 244 Remain 
    sender = None       # 06 Bytes 238 Reamin
    msg = None          # 32 Bytes 206 Remain
    act = 0b00000000    # 01 Bytes 205 Remain
    health_rept= None   # 10 Bytes 195 Remain
    list_node = []    # 195 Bytes 0 Remain  
    if sender != mac_local:
        list_node.append(mac_local) 

    return f"{destination}{sender}{msg}{act}{health_rept}{list_node}"   

def espnow_setup():
    """
    Call once at startup. Initializes WLAN and ESP-NOW.
    Must be called before any other ESP-NOW functions.
    """
    global espnow_instance, mac_local

    sta = network.WLAN(network.WLAN.IF_STA)
    sta.active(True)

    mac_local = sta.config('mac')

    e = espnow.ESPNow()
    e.active(True)

    BROADCAST_MAC = b'\xff\xff\xff\xff\xff\xff'
    e.add_peer(BROADCAST_MAC)

    espnow_instance = e
    print(f"[ESP-NOW] Ready. Local MAC: {format_mac(mac_local)}")
    return espnow_instance


def get_espnow():
    """
    Returns the active ESPNow instance.
    Raises RuntimeError if espnow_setup() hasn't been called yet.
    """
    if espnow_instance is None:
        raise RuntimeError("ESP-NOW not initialized. Call espnow_setup() first.")
    return espnow_instance


def get_local_mac():
    """Returns the local MAC address as bytes."""
    if mac_local is None:
        raise RuntimeError("ESP-NOW not initialized. Call espnow_setup() first.")
    return mac_local


def espnow_send(peer_mac: bytes, packet: bytes):
    """
    Send a packet to a specific peer MAC (as bytes).
    Peer must already be added via espnow_add_peer().
    """
    e = get_espnow()
    try:
        e.send(peer_mac, packet)
    except OSError as err:
        print(f"[ESP-NOW] Send failed to {format_mac(peer_mac)}: {err}")
    

def espnow_add_peer(mac: bytes):
    """Register a peer MAC so we can send to them."""
    e = get_espnow()
    try:
        e.add_peer(mac)
        print(f"[ESP-NOW] Peer added: {format_mac(mac)}")
    except OSError as err:
        print(f"[ESP-NOW] Failed to add peer {format_mac(mac)}: {err}")


def espnow_set_recv_callback(callback):
    """
    Register a callback function triggered on every incoming message.
    Callback signature: callback(mac: bytes, packet: bytes)
    """
    e = get_espnow()
    e.irq(callback)


def espnow_receive(timeout_ms=0):
    """
    Manually poll for a message. Returns (mac, packet) or (None, None).
    timeout_ms=0 means non-blocking.
    """
    e = get_espnow()
    return e.irecv(timeout_ms)


def format_mac(mac: bytes) -> str:
    """Helper: format a MAC bytes object as a readable string."""
    return ':'.join(f'{b:02X}' for b in mac)

def add_peer():
    pass

def choose_peer():
    pass


def recieve_message():s
    pass

def send_message():
    message_packet = create_msg_packet()


def list_peers():
    pass

def save_peers():
    data = {name: mac.hex(':') for name, mac in PEER_DICT.items()}
    
    with open(PEER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_peers():
    global PEER_DICT
    PEER_DICT = {}
    with open(PEER_FILE, "r") as peers:
        data = json.load(peers)

        for name, mac in data.items():
            mac_clean = bytes.fromhex(maca.replace(':', '').replace('-', ''))
            PEER_DICT[name] = mac


def main():
    espnow_setup()
    espnow_set_recv_callback(on_receive)
    load_peers()
    


