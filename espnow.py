import network

import espnow

import json

PEER_FILE = "peer_file.json"
PEER_DICT = {}



mac_local = None

    '''
    Action Items    Bit Pattern Bit Hex     Action     
    Test Comm       0bxxxx xx1x 0x02        Nothing, just sends a test packet              
    Report Home     0b11xx xxxx 0xC0        Message will aslo need to be forwards to home, work down the map
    Add Peer        obxx11 xxxx 0x30        A peer needs to be added to network
    Report Sensor   0bxxxx xxx1 0x01        A sensor is reporting its value to either the home or straight to another sesnor
    Request Action  0bxxxx 1xxx 0x08        An action is being requested 
    Report Action   0bxxxx 11xx 0x0C        An action that has been taken is being reported
    '''

    ''''
    Health Report
    Byte 1: Temp
    Byte 2: Battery Pecentage
    Byte 3 - 6: Live time?
    ...

    Byte 10:
    ''''


def create_msg_packet():
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
    act = 0b0000 0000   # 01 Bytes 205
    health_rept= None   # 10 Bytes 195 Remain
    list_node = []    # 195 Bytes 0 Remain

    if sender != mac_local:
        list_node.append(mac_local)

    return f"{destination}{sender}{msg}{act}{health_rept}{list_node}"




def network_setup():
    global mac_local
    wlan = network.WLAN()
    wlan.active(True)
    mac_local = wlan.config('mac')

def add_peer():
    pass

def choose_peer():
    pass


def recieve_message()
    pass

def send_message():
    pass

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


