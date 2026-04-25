"""
udp_comm.py — UDP communication layer between Raspberry Pi and ESP32.

The RPi sends detection events to the ESP32 over UDP.
The ESP32 can optionally send back acknowledgments or commands.

Protocol (JSON over UDP):
  RPi -> ESP32:
    {"event": "motion"}
    {"event": "person", "confidence": 0.95}
    {"event": "clear"}

  ESP32 -> RPi (optional ack):
    {"ack": "ok"}
    {"cmd": "reboot"}   # future use
"""

import socket
import json
import time
import threading

# ---------------------------------------------------------------------------
# Configuration — update ESP32_IP to match your ESP32's address on the LAN
# ---------------------------------------------------------------------------
ESP32_IP   = "192.168.1.100"   # <-- set this to your ESP32's IP
ESP32_PORT = 5005              # must match the port in your ESP32 firmware
LISTEN_PORT = 5006             # port this Pi listens on for acks / commands
SEND_TIMEOUT = 0.5             # seconds to wait for an ack
# ---------------------------------------------------------------------------


class UDPComm:
    def __init__(self, esp32_ip=ESP32_IP, esp32_port=ESP32_PORT,
                 listen_port=LISTEN_PORT):
        self.esp32_addr = (esp32_ip, esp32_port)

        # Socket used for sending to ESP32
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.send_sock.settimeout(SEND_TIMEOUT)

        # Socket used for receiving acks / commands from ESP32
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.bind(("0.0.0.0", listen_port))
        self.recv_sock.settimeout(1.0)

        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

        print(f"[UDP] Comm ready — sending to {esp32_ip}:{esp32_port}, "
              f"listening on :{listen_port}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_motion(self):
        """Notify ESP32 that motion was detected (before AI runs)."""
        self._send({"event": "motion", "ts": int(time.time())})

    def send_person(self, confidence: float):
        """Notify ESP32 that a person was detected with given confidence."""
        self._send({"event": "person",
                    "confidence": round(float(confidence), 3),
                    "ts": int(time.time())})

    def send_clear(self):
        """Notify ESP32 that the scene is clear (no motion)."""
        self._send({"event": "clear", "ts": int(time.time())})

    def close(self):
        self._running = False
        self.send_sock.close()
        self.recv_sock.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_sock.sendto(data, self.esp32_addr)
            print(f"[UDP] Sent: {payload}")
        except OSError as e:
            print(f"[UDP] Send error: {e}")

    def _recv_loop(self):
        """Background thread: print any message received from the ESP32."""
        while self._running:
            try:
                data, addr = self.recv_sock.recvfrom(1024)
                msg = json.loads(data.decode("utf-8"))
                print(f"[UDP] Received from {addr}: {msg}")
                self._handle_incoming(msg)
            except socket.timeout:
                pass
            except json.JSONDecodeError:
                print(f"[UDP] Non-JSON packet received, ignoring")
            except OSError:
                break  # socket was closed

    def _handle_incoming(self, msg: dict):
        """Handle commands sent from the ESP32 (extensible)."""
        cmd = msg.get("cmd")
        if cmd == "reboot":
            print("[UDP] Reboot command received from ESP32")
            # os.system("sudo reboot") — uncomment to act on it
        elif cmd == "status":
            self._send({"event": "status", "ts": int(time.time())})


if __name__ == "__main__":
    # Quick link test — run this directly on the Pi to verify UDP reach the ESP32.
    # python3 udp_comm.py
    comm = UDPComm()
    try:
        for event_fn, label in [
            (comm.send_motion,          "motion"),
            (lambda: comm.send_person(0.91), "person"),
            (comm.send_clear,           "clear"),
        ]:
            event_fn()
            time.sleep(1)   # give the ESP32 time to ack before next send
        print("[TEST] Done — watch ESP32 serial output for the events.")
        time.sleep(2)       # stay alive long enough to receive any late acks
    finally:
        comm.close()
