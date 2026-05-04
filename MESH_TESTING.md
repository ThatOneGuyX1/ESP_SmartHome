# Mesh Network Testing Guide


End-to-end guide for bringing up the ESP-NOW mesh network and verifying that
nodes can route messages to the host.  Individual node setup (flashing,
calibration, RPi config) is covered in each node's own README — this document
picks up from "all boards are flashed with MicroPython."

---

## How Communication Works

**ESP-NOW does not require a WiFi router.** It is a peer-to-peer protocol that
uses the 802.11 radio hardware directly — nodes talk to each other without
joining any network. The host only needs `WLAN(STA_IF).active(True)` (done
automatically by `espnow_setup()`), not an actual AP connection.

The **only** node that connects to WiFi is the **camera_bridge**, because it
receives UDP packets from the Raspberry Pi over the local network.

The host outputs received mesh data over **USB serial** to the PC — the same
USB cable used for programming. No network connection on the host is needed.

```
RPi ──UDP (WiFi)──► camera_bridge ──┐
                                    ├──ESP-NOW──► Host ESP32 ──USB serial──► PC
           leak_sensor ─────────────┘
```

---

## Network Topology

```
        [Host ESP32]  hop 0  id:1   MAC: 00:4B:12:BE:27:28
              |
    ┌─────────┼──────────────┬──────────────┐
    │         │              │              │
[Light_1]  [room_detect] [camera_bridge] [leak_sensor]
 hop:1 id:5  hop:1 id:2   hop:1 id:10    hop:1 id:11
```

All sensor nodes are one hop from the host. Every node routes toward the host
using `ACT_REPORT_HOME` packets via `smart_esp_comm.py`.

---

## Serial Tools

### Thonny (single board)

Thonny only allows one window at a time — use it when working with a single
board in isolation.

| Action | How |
|---|---|
| Stop running script / open REPL | Red stop button or **Ctrl+C** |
| Upload files | View → Files → right-click → Upload to / |
| Paste into REPL | **Ctrl+V** |
| Soft reset | **Ctrl+D** at `>>>` prompt |

### MobaXterm (multiple boards)

MobaXterm supports multiple serial sessions in separate tabs — recommended
when testing two or more boards at the same time.

**Setup:** Session → Serial → select COM port → Speed: **115200** → OK.
Repeat in a new tab for each board.

| Action | How |
|---|---|
| Stop running script / open REPL | **Ctrl+C** |
| Paste single line into REPL | **Right-click** |
| Paste multi-line block | **Ctrl+E** → paste → **Ctrl+D** |
| Soft reset | **Ctrl+D** at `>>>` prompt |
| Hard reset | Press the physical reset button on the board |

> **Deep sleep:** Ctrl+C cannot wake a sleeping board. Press the physical
> reset button, then quickly Ctrl+C to catch it before `main.py` runs.

### Uploading Files with mpremote (MobaXterm users)

MobaXterm is a terminal only — use **mpremote** from a separate PowerShell or
cmd window to upload files:

```
pip install mpremote
```

Upload files to a board (replace COM5 with your port):
```
mpremote connect COM5 cp main.py smart_esp_comm.py config.json peer_file.json :
```

The `:` means root of the board filesystem. mpremote releases the port after
each command so other MobaXterm tabs stay connected.

```
mpremote connect COM5 ls       # list files on board
mpremote connect COM5 reset    # hard reset
```

### Get a Board's MAC Address

At the `>>>` prompt (Ctrl+C first to stop any running script), paste:

```python
import network; mac = network.WLAN(network.STA_IF).config('mac'); print(':'.join('%02x' % b for b in mac))
```

Paste with right-click in MobaXterm, Ctrl+V in Thonny.

---

## Quick Setup (Recommended)

Instead of manually editing peer files and uploading board by board, use the
setup script. It generates all peer files, injects WiFi credentials, AP channel,
and RPi IP from a single config file, then uploads everything automatically.

**Step 1** — Edit `network_config.json` at the repo root:
```json
{
  "wifi":    { "ssid": "YourNetwork", "password": "YourPassword" },
  "channel": 11,
  "rpi":     { "esp32_ip": "10.254.250.x" },
  "nodes": {
    "host":          { "mac": "XX:XX:XX:XX:XX:XX", "com": "COM7", "hop": 0, "id": 1 },
    "camera_bridge": { "mac": "XX:XX:XX:XX:XX:XX", "com": "COM5", "hop": 1, "id": 10 },
    "leak_sensor":   { "mac": "XX:XX:XX:XX:XX:XX", "com": "COM5", "hop": 1, "id": 11 }
  }
}
```

**Step 2** — Run from the repo root:
```
python setup.py
```

The script will generate peer files, inject all settings, and ask if you want
to upload to boards. Answer `y` and it handles everything.

> To find a board's MAC: connect it, Ctrl+C for REPL, paste:
> ```python
> import network; mac = network.WLAN(network.STA_IF).config('mac'); print(':'.join('%02x' % b for b in mac))
> ```
> To find AP channel: boot camera_bridge, Ctrl+C for REPL, paste:
> ```python
> import network; print(network.WLAN(network.STA_IF).config('channel'))
> ```

The manual steps below are only needed if you're configuring a single node
or troubleshooting.

---

## Files Required on Each Board

| Board | Files to upload |
|---|---|
| **Host** | `smart_esp_comm.py`, `config.json`, `peer_file.json`, `main.py` |
| **camera_bridge** | `smart_esp_comm.py`, `camera_mesh.py`, `config.json`, `peer_file.json`, `main.py` |
| **leak_sensor** | `smart_esp_comm.py`, `config.json`, `peer_file.json`, `main.py` |
| **room_detect** | `smart_esp_comm.py`, `config.json`, `peer_file.json`, `main.py`, + sensor libs |

Always use the latest `smart_esp_comm.py` from `ESP-Now_Comm_Packet/` — it
must be the same version on every board.

---

## Step 1 — Verify peer_file.json on Each Board

Each node needs to know about its direct neighbor(s) before routing will work.
The `peer_file.json` on every sensor node should contain at least the host:

```json
{
  "peers": {
    "host": {
      "mac": "00:4B:12:BE:27:28",
      "neighbors": ["<this-node-name>"],
      "hop": 0,
      "id": 1
    }
  }
}
```

Replace `<this-node-name>` with the actual node name (e.g. `"camera_bridge"`).
The `neighbors` field is what tells `smart_esp_comm` that this node is a direct
ESP-NOW peer of the host — routing depends on it.

The **host's** `peer_file.json` (`Nodes/host/peer_file.json`) must list every
node that will send it packets:

```json
{
  "peers": {
    "camera_bridge": { "mac": "00:4B:12:BD:58:C0", "neighbors": ["host"], "hop": 1, "id": 10 },
    "leak_sensor":   { "mac": "<fill in>",          "neighbors": ["host"], "hop": 1, "id": 11 },
    "light_1":       { "mac": "B8:F8:62:D5:D3:88",  "neighbors": ["host"], "hop": 1, "id": 5  },
    "room_detect":   { "mac": "B8:F8:62:D5:44:04",  "neighbors": ["host"], "hop": 1, "id": 2  }
  }
}
```

---

## Step 2 — Boot the Host

Connect the host ESP32 via USB. Open a serial session (Thonny or MobaXterm on
the host's COM port at 115200). Upload this as `main.py` on the host then
hard-reset:

```python
import smart_esp_comm as sh
sh.boot()
print("[HOST] Listening...")
while True:
    sh.poll_serial()
```

On boot you should see:

```
[ESP-NOW] Ready. MAC: 00:4B:12:BE:27:28
[CONFIG] Identity: 'host' | hop 0 | ID 1
[PEERS] Loaded 4 peers.
[BOOT] Node ready.
[HOST] Listening...
```

If peer count is wrong, check that `peer_file.json` was uploaded correctly.

---

## Step 3 — Boot a Sensor Node

Connect the sensor node via USB, open a second serial session on its COM port,
and hard-reset it. Expected output:

```
[WiFi] Connected — 10.254.250.x          ← camera_bridge only
[ESP-NOW] Ready. MAC: 00:4B:12:BD:58:C0
[CONFIG] Identity: 'camera_bridge' | hop 1 | ID 10
[PEERS] Loaded 1 peers.
[BOOT] Node ready.
[UDP] Listening on port 5005
```

For non-WiFi nodes (leak_sensor) you'll see ESP-NOW ready and boot, no WiFi
line.

---

## Step 4 — Trigger a Test Packet from REPL

Hit Ctrl+C on the sensor node to stop `main.py` and open the REPL. This tests
the full routing path without needing the RPi or a real sensor event.

**Camera bridge** — paste into REPL:
```python
import camera_mesh
camera_mesh.on_person(0.9)
```

**Leak sensor** — paste into REPL (use Ctrl+E / Ctrl+D in MobaXterm for
multi-line):
```python
import smart_esp_comm as sh
sh.espnow_setup(); sh.load_config(); sh.load_peers()
next_hop = sh._find_next_hop_toward_home()
host_mac = sh.mac_bytes("00:4B:12:BE:27:28")
pkt = sh.create_msg_packet(dest_mac=host_mac, action=sh.ACT_REPORT_HOME,
                            message=b"LEAK:3100", health=None, trail=[])
sh.espnow_send(next_hop, pkt)
```

**On the host serial output you should see:**
```json
{"type": "sensor_report", "sender": "00:4B:12:BD:58:C0", "message": "CAM:PERSON:90", "trail": [10], "health": {}, "timestamp": null}
```

If this JSON line appears on the host, end-to-end routing is working.

---

## Step 5 — Add a Node via Serial Commands (Alternative to editing peer_file.json)

Instead of editing `peer_file.json` manually, provision peers live by typing
directly into the host's REPL:

```
ADD camera_bridge 00:4B:12:BD:58:C0 1 10 host
ADD leak_sensor   <mac>              1 11 host
LIST
SYNC
```

`ADD <name> <mac> <hop> <id> <neighbors>` — adds the peer and saves to
`peer_file.json` automatically.  
`SYNC` — broadcasts the full peer map to all registered neighbors.  
`LIST` — prints everything currently in the peer map.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `[PEERS] Loaded 0 peers.` | `peer_file.json` missing or not uploaded | Re-upload the file, hard reset |
| `[ROUTE] No neighbor closer to home found` | Node's peer_file doesn't list host, or host's `neighbors` field doesn't include this node name | Check `peer_file.json` — the host entry must have `"neighbors": ["<this-node>"]` |
| `[ESP-NOW] Send failed` | Host not registered as an ESP-NOW peer | `load_peers()` registers neighbors automatically — check peer_file is correct |
| `[WARN] Packet from unknown MAC — rejected` | Host received a packet from a node not in its peer_file | Add the node to host's peer_file.json and re-upload |
| Camera bridge drops WiFi after boot | `sh.boot()` was called (disconnects WiFi) | camera_bridge/main.py already works around this — make sure you uploaded the latest version |
| `[SYNC] WARNING: sync packet is NNNb, exceeds 250B` | Too many peers in the map for one ESP-NOW packet | Remove unused peers with `REMOVE <name>` |
| Host prints nothing on receive | Channel mismatch — host and camera_bridge on different channels | See Channel Note below |

---

## Channel Note

ESP-NOW and WiFi share the same radio. The camera_bridge connects to WiFi
first and ESP-NOW adopts the AP's channel. All other nodes (host, leak_sensor,
etc.) default to **channel 6** via `espnow_setup()`.

If your WiFi AP is NOT on channel 6 (common — most routers use ch1, 6, or 11),
the host and camera_bridge will be on different channels and can't communicate.

**Fix — check your AP channel first:**

On the camera_bridge, after boot, run in REPL:
```python
import network; print(network.WLAN(network.STA_IF).config('channel'))
```

Then update `Nodes/host/main.py` to match. After `sh.espnow_setup()` add:
```python
import network
_sta = network.WLAN(network.STA_IF)
_sta.config(channel=11)  # replace 11 with your AP's channel
print("[HOST] Channel:", _sta.config('channel'))
```

Upload to the host and verify the channel prints correctly on boot.

> Pure ESP-NOW nodes (leak_sensor, room_detect) use channel 6 by default.
> If your AP is on a different channel, update `sta.config(channel=N)` in
> `espnow_setup()` inside `smart_esp_comm.py` to match, then re-upload
> `smart_esp_comm.py` to all boards.
