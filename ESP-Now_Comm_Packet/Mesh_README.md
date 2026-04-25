# ESP-NOW Mesh Network — Project Documentation

## Overview

This project implements a peer-to-peer smart home monitoring and control system built on ESP32 microcontrollers running MicroPython. A Host PC connects to a Host ESP32 over USB serial, giving it access to a private ESP-NOW mesh network. Sensor nodes spread throughout the home relay data and commands across the mesh, with each node forwarding messages to nodes further from or closer to the host as needed.

The entire system is managed through a single MicroPython module: `smart_esp_comm.py`. Each ESP32 runs the same file. Identity and network role are defined by two JSON configuration files stored on the device.

---

## Architecture

### Roles

**Host PC**
The user-facing side of the system. Sends provisioning and management commands to the Host ESP over USB serial using plain text commands. Holds the authoritative master peer list.

**Host ESP (hop 0)**
The bridge between the Host PC and the ESP-NOW mesh. Receives serial commands from the PC, maintains its own local peer map, and propagates updates outward through the network. Always assigned hop 0.

**Sensor Nodes (hop 1+)**
Any ESP32 that is not the Host ESP. Each node knows its direct neighbors and its hop distance from the host. Nodes relay packets and peer list updates outward away from the host, and relay sensor data and reports back toward the host.

### Network Topology

Nodes are arranged in a hop-based tree rooted at the Host ESP. Each node knows two things: who its direct neighbors are, and how far it is from the host. This hop count drives all routing decisions.

```
Host PC
   |
   | USB Serial
   |
Host ESP  (hop 0)
   |
   +-- Living Room  (hop 1)
   |      |
   |      +-- Kitchen   (hop 2)
   |      +-- Hallway   (hop 2)
   |
   +-- Garage  (hop 1)
          |
          +-- Garden  (hop 2)
```

A node at hop 2 will forward peer list updates to hop 3 neighbors but never back to hop 1. This prevents updates from bouncing back toward the host without needing a visited-node list.

---

## File Structure

### On Each ESP32

```
main.py               Entry point. Calls boot() and runs the main loop.
smart_esp_comm.py     The entire communication library.
{SENSOR_NAME}_config.json      This node's fixed identity. Set once at provisioning.
peer_file.json        The full network map. Updated dynamically by sync packets.
```

### {SENSOR_NAME}_config.json

Stores the node's identity. Written once when the node is provisioned and does not change unless you reprovision.

```json
{
    "name": "kitchen",
    "hop":  2,
    "id":   4
}
```

- `name` — human readable label for this node
- `hop` — distance from the Host ESP in hops
- `id` — unique 1-byte integer (1-255) assigned at provisioning. ID 0 is reserved as an empty slot marker in the hop trail and must never be assigned to a node.

### peer_file.json

Stores the full known network map. Written every time the peer list changes. Rebuilt automatically by sync packets propagating through the mesh.

```json
{
    "peers": {
        "living_room": {
            "mac":       "AA:BB:CC:DD:EE:FF",
            "neighbors": ["host", "kitchen", "hallway"],
            "hop":       1,
            "id":        3
        },
        "kitchen": {
            "mac":       "BB:CC:DD:EE:FF:AA",
            "neighbors": ["living_room"],
            "hop":       2,
            "id":        4
        }
    }
}
```

---

## Packet Format

Every standard message packet is exactly 67 bytes. Fixed fields are always present. The health block is optional and its presence is signalled by the flags byte.

```
Bytes   Size    Field
----------------------------------------------------------------------
0-5     6B      Destination MAC address
6-11    6B      Sender MAC address
12      1B      Action byte
13      1B      Message length (0-32)
14-45   32B     Message payload (sensor-defined format)
46      1B      Flags byte (bit 0 = health block present)
47-56   10B     Health report (optional, zeroed if absent)
57-66   10B     Hop trail (10 x 1-byte node IDs, 0x00 = empty slot)
----------------------------------------------------------------------
Total   67B
```

### Action Bytes

The action byte tells the receiver what to do with the packet. Each packet carries exactly one action byte.

```
Constant        Hex     Binary          Purpose
----------------------------------------------------------------------
ACT_SENSOR_RPT  0x01    0b0000_0001     Sensor reporting a value
ACT_TEST        0x02    0b0000_0010     Test ping, no action taken
ACT_REQ_ACTION  0x08    0b0000_1000     Requesting an action be performed
ACT_RPT_ACTION  0x0C    0b0000_1100     Reporting a completed action
ACT_ADD_PEER    0x30    0b0011_0000     A new peer needs to be added
ACT_SYNC_PEERS  0x50    0b0101_0000     Full peer map sync packet
ACT_REPORT_HOME 0xC0    0b1100_0000     Message to be forwarded to host
```

### Message Payload

The 32-byte message field is sensor-defined. Each sensor type has its own binary layout that all other nodes know how to decode based on the sender's identity. The message length byte tells the receiver how many of the 32 bytes are meaningful — a sensor using only 8 bytes sets this to 8, and the rest of the field is ignored.

### Health Report (optional, 10 bytes)

```
Byte 0      Signed int      Temperature in degrees (-128 to 127)
Byte 1      Unsigned int    Battery percentage (0 to 100)
Bytes 2-5   Unsigned 32bit  Uptime in seconds
Bytes 6-9   Reserved        Zeroed, reserved for future use
```

The flags byte at position 46 controls whether this block contains valid data. Bit 0 set means health data is present. All other bits are reserved for future optional blocks.

### Hop Trail (10 bytes)

Tracks which nodes a packet has passed through. Each node appends its own 1-byte ID when it handles or forwards a packet. Empty slots are filled with 0x00. The receiver reads until it hits a 0x00 or exhausts the 10 slots.

The trail serves two purposes. First, it prevents routing loops — if a node sees its own ID already in the trail it logs a warning. Second, it gives the host a complete picture of the path a packet took through the mesh, which is useful for debugging and network health monitoring.

---

## Peer List Propagation

When the Host PC adds or removes a peer, the update needs to reach every node in the network. The propagation works as follows:

1. Host PC sends an ADD or REMOVE command over serial.
2. Host ESP updates its local peer map and saves it to `peer_file.json`.
3. Host ESP calls `sync_peers_outward()`, which sends the full peer map to all direct neighbors with a hop count greater than its own.
4. Each receiving node merges the incoming map into its local map, saves, and calls `sync_peers_outward()` itself.
5. The update continues outward until it reaches nodes with no outward neighbors.

Because nodes only forward to neighbors with a higher hop count, the update never travels back toward the host. No coordination or visited-node tracking is needed.

Sync packets use their own raw format rather than the standard 67-byte packet structure, since they need to carry the full JSON peer map. The first byte is always `ACT_SYNC_PEERS` (0x50), followed by the JSON-encoded peer dict. The ESP-NOW 250-byte hard limit applies — for large networks a compact binary sync format should replace the JSON encoding.

---

## Serial Commands

The Host PC communicates with the Host ESP over USB serial at 115200 baud (8N1). Commands are plain text, one per line, terminated by a newline character.

### Provisioning Commands

Set this node's identity and save to `node_config.json`. Run these once on each fresh node before anything else.

```
SETNAME <name>
```
Sets the node's human readable name.
```
SETNAME kitchen
```

```
SETHOP <hop>
```
Sets the node's hop distance from the host.
```
SETHOP 2
```

```
SETID <id>
```
Sets the node's unique 1-byte ID. Must be unique across the entire network. Do not use 0.
```
SETID 4
```

### Network Map Commands

```
ADD <name> <mac> <hop> <id> <neighbors>
```
Adds a peer to the network map. Neighbors are comma-separated with no spaces. Automatically propagates the update through the mesh.
```
ADD kitchen BB:CC:DD:EE:FF:AA 2 4 living_room,hallway
```

```
REMOVE <name>
```
Removes a peer from the map and cleans up neighbor references. Automatically propagates.
```
REMOVE kitchen
```

### Utility Commands

```
LIST
```
Prints all known peers, their MAC address, hop count, ID, and whether they are a direct neighbor of this node.

```
SYNC
```
Manually pushes the current peer map outward through the mesh. Useful after making several changes at once.

---

## Serial Connection Settings

```
Baud Rate:    115200
Data Bits:    8
Parity:       None
Stop Bits:    1
Flow Control: None
```

This is commonly written as 115200 8N1.

### Finding the Port

On Windows the ESP32 appears as a COM port. Check Device Manager under Ports (COM and LPT). On Linux it is usually `/dev/ttyUSB0` or `/dev/ttyACM0`. On Mac it is usually `/dev/cu.usbserial-XXXX` or `/dev/cu.SLAB_USBtoUART`. Run `ls /dev/cu.*` before and after plugging in to identify it.

### Recommended Tools

- Thonny — use for flashing and reading boot output only, not for sending serial commands while the main loop is running
- PuTTY (Windows) — set connection type to Serial
- screen (Linux/Mac) — `screen /dev/ttyUSB0 115200`

---

## Provisioning a New Node

This is the full sequence for adding a brand new ESP32 to the network.

**Step 1 — Flash the firmware**
Copy `smart_esp_comm.py` to the device using Thonny or ampy.

**Step 2 — Create main.py**
```python
import smart_esp_comm

smart_esp_comm.boot()

while True:
    smart_esp_comm.poll_serial()
```

**Step 3 — Provision identity over serial**
Connect with PuTTY or screen after closing Thonny. Hard reset the device and send:
```
SETNAME kitchen
SETHOP 2
SETID 4
```

**Step 4 — Add its neighbors**
```
ADD living_room AA:BB:CC:DD:EE:FF 1 3 host,kitchen
```

**Step 5 — Verify and sync**
```
LIST
SYNC
```

**Step 6 — Add this node to its neighbors**
On each neighboring node, run:
```
ADD kitchen BB:CC:DD:EE:FF:AA 2 4 living_room
SYNC
```

---

## Thonny Conflict Warning

Thonny uses the USB serial port to communicate with MicroPython's REPL. If your main loop is running and you attempt to type serial commands into Thonny's shell, Thonny and your code will fight over the port and Thonny will throw a `ProtocolError`.

The correct workflow is:

1. Write and flash code using Thonny.
2. Read boot output in Thonny's shell.
3. Stop the program in Thonny with Ctrl+C.
4. Close Thonny entirely.
5. Open PuTTY or screen on the same COM port.
6. Hard reset the ESP32.
7. Send serial commands freely.

For development testing without leaving Thonny, hardcode commands directly in `main.py`:

```python
import smart_esp_comm

smart_esp_comm.boot()

smart_esp_comm.handle_serial_command("ADD living_room AA:BB:CC:DD:EE:FF 1 3 host")
smart_esp_comm.handle_serial_command("LIST")

while True:
    smart_esp_comm.poll_serial()
```

---

## API Reference

### Boot

```python
smart_esp_comm.boot()
```
Full boot sequence. Initializes ESP-NOW, loads node identity, loads peer map, and registers the receive callback. Call once from `main.py` before the main loop.

### Packet Building

```python
create_msg_packet(dest_mac, action, message, health, trail)
```
Builds a full 67-byte packet. Returns bytes.

- `dest_mac` — 6-byte destination MAC
- `action` — action byte constant
- `message` — up to 32 bytes, sensor-defined format
- `health` — optional dict with keys `temp`, `battery`, `uptime`. Pass `None` to omit.
- `trail` — list of node IDs already visited. Pass `[]` to start fresh.

```python
parse_packet(pkt)
```
Decodes a raw 67-byte packet into a dict with keys: `dest`, `sender`, `action`, `msg_len`, `message`, `flags`, `health`, `trail`.

### Sending and Forwarding

```python
espnow_send(peer_mac, packet)
```
Send raw bytes to a registered peer MAC.

```python
forward_packet(pkt, next_hop_mac)
```
Forward a parsed packet dict to the next hop. Preserves original destination, drops health block, appends this node's ID to the trail.

### Peer Management

```python
add_peer(name, mac_str, neighbors, hop, node_id)
```
Add or update a peer in the local map. Registers with ESP-NOW if a direct neighbor. Saves automatically.

```python
remove_peer(name)
```
Remove a peer and clean up neighbor references. Saves automatically.

```python
list_peers()
```
Print all known peers to the console.

```python
sync_peers_outward()
```
Push the full peer map to all outward neighbors.

### Health

```python
decode_health(pkt)
```
Extract the health block from a raw packet. Returns dict with `temp`, `battery`, `uptime`.

### Serial

```python
poll_serial()
```
Non-blocking UART poll. Call every iteration of the main loop on the Host ESP.

```python
handle_serial_command(line)
```
Parse and execute a single serial command string. Useful for hardcoding test commands during development.

---

## Known Limitations and Future Work

**250-byte sync packet limit**
The peer list sync packet uses JSON encoding. As the network grows, the JSON representation will approach and eventually exceed the ESP-NOW 250-byte hard limit. A compact binary encoding for sync packets should be implemented before deploying more than approximately 8 to 10 nodes.

**No acknowledgement or retry**
ESP-NOW is fire-and-forget. A sync packet or sensor report can be silently lost with no indication to the sender. A lightweight acknowledgement and retry system should be added for reliability.

**Power loss during file write**
`save_peers()` overwrites the peer file in a single write operation. A power loss mid-write will corrupt the file. Writing to a temporary file and renaming it atomically would protect against this, subject to MicroPython filesystem support on the target board.

**ID 0 is reserved**
Node ID 0 is used as the empty slot marker in the hop trail byte array. No node may be assigned ID 0. IDs run from 1 to 255, giving a maximum network size of 255 nodes.

**Neighbor lists are manually maintained**
Neighbors are defined at provisioning time and do not update automatically if the physical network topology changes. If a node is moved or replaced, neighbor lists on adjacent nodes must be updated manually and a sync pushed.