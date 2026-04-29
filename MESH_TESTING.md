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
cable used by Thonny. No network connection on the host is needed.

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

All sensor nodes are one hop from the host.  Every node routes toward the host
using `ACT_REPORT_HOME` packets via `smart_esp_comm.py`.

---

## Files Required on Each Board

Upload via Thonny → View → Files → right-click file → Upload to /

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

> **Finding a node's MAC:** Connect the board in Thonny and run:
> ```python
> import network; print(network.WLAN(network.STA_IF).config('mac').hex(':'))
> ```
> Or just read it from the esptool output when you flashed the board.

---

## Step 2 — Boot the Host

Connect the host ESP32 in Thonny. For a simple receive-and-print listener,
upload this as `main.py` on the host:

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

Connect the sensor node (e.g. camera_bridge) in Thonny and hard-reset it.
Expected output:

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

With the sensor node connected in Thonny, open the REPL (Ctrl+C to stop, then
use the shell at the bottom). This tests the full routing path without needing
the RPi or a real leak event.

**Camera bridge:**
```python
import camera_mesh
camera_mesh.on_person(0.9)
```

**Leak sensor:**
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

Instead of editing peer_file.json manually, you can provision peers live using
the host's serial interface from Thonny's REPL:

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
| Host prints nothing on receive | Wrong channel — camera_bridge WiFi AP and mesh nodes on different channels | All pure ESP-NOW nodes default to channel 6 via `espnow_setup()`; camera_bridge adopts the AP's channel — AP must also be on ch6 |

---

## Channel Note

ESP-NOW and WiFi share the same radio. All nodes that use `espnow_setup()`
directly (host, leak_sensor, room_detect, light_1) default to **channel 6**.
The camera_bridge connects to WiFi first and adopts the AP's channel — so
**your WiFi router/AP must be on channel 6** for camera_bridge to reach the
rest of the mesh.  Check your router settings if camera_bridge packets never
arrive at the host.
