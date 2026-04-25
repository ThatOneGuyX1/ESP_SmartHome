# Leak Sensor Node

Water leak detection using an analog resistive leak sensor on an ESP32 Feather V2.
The board spends almost all its time in deep sleep (~10 µA) and only wakes to
check the sensor and send a UDP alert on detection.

---

## Hardware

- ESP32 Feather V2
- Resistive water/leak sensor (single analog output wire)
- Sensor analog out → **A0 (GPIO26)**  — change pin in code if using a different pin

---

## Files

| File | Purpose |
|---|---|
| `leak_sensor.py` | Calibration tool — run this first to find your threshold |
| `main.py` | Production code — timer-based deep sleep + mesh alert |
| `config.json` | Node identity (name, hop, id) — edit before uploading |

---

## Step 1 — Calibrate with leak_sensor.py

Before deploying, you need to know the ADC values your sensor reads when dry
vs wet so you can set a reliable threshold.

Upload and run `leak_sensor.py` in Thonny. Watch the serial output:

```
Dry — ADC=180
Dry — ADC=175
Dry — ADC=182
```

Then dip the sensor in water:

```
LEAK DETECTED — ADC=3100
LEAK DETECTED — ADC=3250
```

Pick a threshold **between** your dry and wet values — e.g. if dry is ~180
and wet is ~3100, set `LEAK_THRESHOLD = 1000`.

---

## Step 2 — Configure main.py

Open `main.py` and update the config section:

```python
POLL_INTERVAL_S = 5      # how often to wake and check (seconds)
LEAK_THRESHOLD  = 1000   # ADC value from calibration step above
ALERT_HOLDOFF_S = 30     # gap between repeated alerts on sustained leak
```

Change the pin if not using A0:
```python
adc = machine.ADC(machine.Pin(26))   # A0=26, A1=25, A2=34, A3=39, A4=36, A5=4
```

Edit `config.json` to set this node's identity:
```json
{
    "name": "leak_sensor",
    "hop": 1,
    "id": 11
}
```
Adjust `hop` and `id` to match your network. `id` must be unique across all nodes.

---

## Step 3 — Flash to board

Upload these files to the board via Thonny (**View → Files**, right-click → **Upload to /**):

| File | From |
|---|---|
| `main.py` | `leak_sensor/main.py` |
| `config.json` | `leak_sensor/config.json` |
| `smart_esp_comm.py` | `ESP-Now_Comm_Packet/smart_esp_comm.py` |

`peer_file.json` is created automatically during provisioning.

> **Important:** You must upload `main.py` to the board's flash before running.
> Do not run it directly from Thonny using F5.
>
> When the board enters deep sleep, Thonny loses the USB connection. On wake
> the board boots from its own flash — if `main.py` was only run from Thonny
> and not uploaded, the board has nothing to run and appears stuck/dead.
>
> After uploading, hard reset the board. You will see it wake, check the ADC,
> sleep, and repeat. Thonny may not show output after the first sleep — this
> is normal. The board is still cycling correctly.

---

## How it works

Every wake cycle the board runs `main.py` top to bottom:

```
Wake from deep sleep
        │
        ▼
Read ADC
        │
        ├── Dry (ADC < threshold)
        │       │
        │       └── deepsleep(POLL_INTERVAL_S)   ← back to sleep fast
        │
        └── Wet (ADC >= threshold)
                │
                ▼
        Connect WiFi
                │
                ▼
        Send UDP alert {"event": "leak", "adc": val}
                │
                └── deepsleep(ALERT_HOLDOFF_S)   ← longer sleep to avoid spam
```

**Power savings:** The board is in deep sleep (~10 µA) between checks. At a
5 second poll interval the average current is well under 1 mA — battery life
is measured in weeks rather than hours.

> Note: this uses `machine.deepsleep()` (timer-based wake), not the ESP32's
> true ULP coprocessor. Power savings are nearly identical for this use case.

---

## Mesh Alert Format

When a leak is detected the node sends an `ACT_REPORT_HOME` packet toward
the host using hop-based routing. The message field contains:

```
"LEAK:3100"   ← LEAK:<adc_value>
```

The host receives this and prints it as a JSON sensor report to the PC.

---

## Pin Reference (Feather V2)

| Label | GPIO | Notes |
|---|---|---|
| A0 | 26 | default |
| A1 | 25 | |
| A2 | 34 | input only |
| A3 | 39 | input only |
| A4 | 36 | input only |
| A5 | 4 | |
