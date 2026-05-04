## Health Report

The health report is a fixed **10-byte field** inside each ESP-NOW message packet. It gives the host node a quick summary of the sensor node’s operating condition without using the 32-byte sensor message payload.

### Health Report Byte Layout

| Bytes | Field | Size | Description |
| --- | --- | --- | --- |
| 0 | Temperature | 1 byte | Signed integer temperature value in Celsius |
| 1 | Battery | 1 byte | Battery state of charge, 0–100% |
| 2–5 | Uptime | 4 bytes | Node runtime in seconds |
| 6–9 | Reserved | 4 bytes | Zero-filled for future expansion |

### Example Decoded Health Output

```python
{'battery': 97, 'uptime': 12903, 'temp': 32}

