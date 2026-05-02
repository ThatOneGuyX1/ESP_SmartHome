# Personal Testing Cheatsheet

## Board Reference

| Board | COM | MAC |
|---|---|---|
| Host | COM7 | 00:4B:12:BD:57:84 |
| COM5 board | COM5 | 00:4B:12:BD:58:C0 |

WiFi: ` ` / ``  
WiFi AP channel: **11** (host main.py hardcoded to ch11 to match)

---

## Flash COM5 as Leak Sensor

```
python -m mpremote connect COM5 cp leak_sensor/main.py :main.py
python -m mpremote connect COM5 cp leak_sensor/config.json :config.json
python -m mpremote connect COM5 cp leak_sensor/peer_file.json :peer_file.json
python -m mpremote connect COM5 cp ESP-Now_Comm_Packet/smart_esp_comm.py :smart_esp_comm.py
```

## Flash COM5 as Camera Bridge

```
python -m mpremote connect COM5 cp esp32_rpi_bridge/main.py :main.py
python -m mpremote connect COM5 cp esp32_rpi_bridge/camera_mesh.py :camera_mesh.py
python -m mpremote connect COM5 cp esp32_rpi_bridge/config.json :config.json
python -m mpremote connect COM5 cp esp32_rpi_bridge/peer_file.json :peer_file.json
python -m mpremote connect COM5 cp ESP-Now_Comm_Packet/smart_esp_comm.py :smart_esp_comm.py
```

## Flash Host (COM7)

```
python -m mpremote connect COM7 cp Nodes/host/main.py :main.py
python -m mpremote connect COM7 cp Nodes/host/config.json :config.json
python -m mpremote connect COM7 cp Nodes/host/peer_file.json :peer_file.json
python -m mpremote connect COM7 cp ESP-Now_Comm_Packet/smart_esp_comm.py :smart_esp_comm.py
```

---

## RPi Commands

```bash
# SSH in
ssh pi@<pi-ip>

# Run detection
cd ~/ESP_SmartHome/rpi
source env/bin/activate
python detection_v2.py

# Run tuning UI (open http://<pi-ip>:8000)
python tuning.py

# Test UDP manually (no camera needed)
python udp_comm.py
```

---

## REPL Quick Tests

**Get MAC:**
```python
import network; mac = network.WLAN(network.STA_IF).config('mac'); print(':'.join('%02x' % b for b in mac))
```

**Trigger camera person event manually:**
```python
import camera_mesh
camera_mesh.on_person(0.9)
```

**Trigger leak event manually:**
```python
import smart_esp_comm as sh
sh.espnow_setup(); sh.load_config(); sh.load_peers()
next_hop = sh._find_next_hop_toward_home()
host_mac = sh.mac_bytes("00:4B:12:BD:57:84")
pkt = sh.create_msg_packet(dest_mac=host_mac, action=sh.ACT_REPORT_HOME, message=b"LEAK:3100", health=None, trail=[])
sh.espnow_send(next_hop, pkt)
```

---

## MobaXterm Serial

- COM5: Session → Serial → COM5 → 115200
- COM7: Session → Serial → COM7 → 115200
- Paste single line: right-click
- Paste multi-line: Ctrl+E → paste → Ctrl+D
- Stop script / REPL: Ctrl+C
- Soft reset: Ctrl+D at `>>>`

---

## mpremote Tips

- Port busy? Close the MobaXterm tab for that COM port first
- Board running main.py? Hold BOOT button while plugging in to prevent autorun
- Check files on board: `python -m mpremote connect COM5 ls`
- Read file: `python -m mpremote connect COM5 cat :main.py`
