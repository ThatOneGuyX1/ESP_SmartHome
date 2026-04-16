import network
import espnow
import json
import time

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
'''

'''
Health Report
Byte 1: Temp
Byte 2: Battery Pecentage
Byte 3 - 6: Live time?


Byte 10:
'''


def create_msg_packet(dest,send,message,health,list_node =None, act = 0xC0): #Our baseline action is reporting to home
    '''
    The message packet is designed to provide a custom format for out esp messages. One format can also accomplish many things in on packet
    We first include the start and end points of the message (Destaionation and Sender) (12 Bytes total)
    We then include as 32 Byte message
    Action item is saying what the message is supoosed to do
    We can also send a health update on top of this. Messages between sensors do not need to do anything with this info
    We can then hold a list of 32 other Nodes that we have passed trough.
    ''' 
    msg_bytes = message.encode()

    if len(msg_bytes) > 200:
        msg_bytes = msg_bytes[:200] 

    packet = bytearray()

    packet += dest
    packet += send
    packet += bytes([act])
    packet += bytes([health.get("bat", 0)])

    timestamp = time.ticks_ms() & 0xFFFFFFFF
    packet += timestamp.to_bytes(4, 'big') # 4 bytes

    packet += bytes([len(msg_bytes)])
    packet += msg_bytes

    return packet
    
    ## Total length is 250 Byters
    #destination = None  # 06 Bytes 244 Remain 
    #sender = None       # 06 Bytes 238 Reamin
    #msg = None          # 32 Bytes 206 Remain
    #act = 0b00000000    # 01 Bytes 205 Remain
    #health_rept= None   # 10 Bytes 195 Remain
    #list_node = []    # 195 Bytes 0 Remain  
    #if sender != mac_local:
    #    list_node.append(mac_local) 

    #return f"{destination}{sender}{msg}{act}{health_rept}{list_node}"   

def parse_msg_packet(packet: bytes):
    try:
        dest = packet[0:6]
        sender = packet[6:12]
        act = packet[12]
        battery = packet[13]

        timestamp = int.from_bytes(packet[14:18], 'big')

        msg_len = packet[18]
        msg = packet[19:19+msg_len].decode()

        return {
            "destination": format_mac(dest),
            "sender": format_mac(sender),
            "action": act,
            "battery": battery,
            "timestamp": timestamp,
            "message": msg
        }

    except Exception as e:
        print("[PARSE ERROR]", e)
        return None

def espnow_setup():
    """
    Call once at startup. Initializes WLAN and ESP-NOW.
    Must be called before any other ESP-NOW functions.
    """
    global espnow_instance, mac_local

    sta = network.WLAN(network.WLAN.IF_STA)
    sta.active(True)

    sta.disconnect()
    sta.config(channel=6)

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

    print("Sending lenght: ", len(packet))
    print("Type: ", type(packet))

    if len(packet) > 250:
        print("[ERROR] Packet too large: ", len(packet))
        return

    try:
        e.send(peer_mac, bytes(packet))
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


recv_queue = []

def espnow_set_recv_callback():
    """
    Register a callback function triggered on every incoming message.
    Callback signature: callback(mac: bytes, packet: bytes)
    """
    e = get_espnow()
    #e.irq(callback)

    def _internal_callback(_):
        result = e.irecv(0)
        if result:
            recv_queue.append(result)

    e.irq(_internal_callback)


def get_next_packet():
    if recv_queue:
        return recv_queue.pop(0)
    return None


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


def recieve_message():
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

    try:
        with open(PEER_FILE, "r") as peers:
            data = json.load(peers)

            for name, mac in data.items():
                mac_clean = bytes.fromhex(mac.replace(':', ''))
                PEER_DICT[name] = mac

    except:
        print("[ESP-NOW] No peer file found.")


#def main():
#    espnow_setup()
#    espnow_set_recv_callback(on_receive)
#    load_peers() 



