"""
setup.py — One-shot network configuration tool.

Edit network_config.json for your location, then run:
    python setup.py

This script will:
  1. Generate peer_file.json for every node
  2. Inject WiFi credentials into camera_bridge/main.py
  3. Inject AP channel into Nodes/host/main.py
  4. Inject ESP32 IP into rpi/udp_comm.py
  5. Upload all files to each board via mpremote

Requirements: pip install mpremote
"""

import json
import re
import subprocess
import sys
import os

CONFIG_FILE = "network_config.json"

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def generate_peer_file(node_name, nodes):
    """
    Build peer_file.json for a given node.
    Star topology: sensor nodes know only the host.
                   host knows all sensor nodes.
    """
    peers = {}
    host = nodes["host"]

    if node_name == "host":
        for name, entry in nodes.items():
            if name == "host":
                continue
            peers[name] = {
                "mac":       entry["mac"].upper(),
                "neighbors": ["host"],
                "hop":       entry["hop"],
                "id":        entry["id"]
            }
    else:
        peers["host"] = {
            "mac":       host["mac"].upper(),
            "neighbors": [node_name],
            "hop":       host["hop"],
            "id":        host["id"]
        }

    return {"peers": peers}


def write_peer_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Written: {path}")


def inject_wifi(cfg):
    path = "esp32_rpi_bridge/main.py"
    with open(path) as f:
        content = f.read()
    content = re.sub(r'WIFI_SSID\s*=\s*".*?"',
                     f'WIFI_SSID     = "{cfg["wifi"]["ssid"]}"', content)
    content = re.sub(r'WIFI_PASSWORD\s*=\s*".*?"',
                     f'WIFI_PASSWORD = "{cfg["wifi"]["password"]}"', content)
    with open(path, "w") as f:
        f.write(content)
    print(f"  WiFi credentials injected → {path}")


def inject_channel(cfg):
    path = "Nodes/host/main.py"
    with open(path) as f:
        content = f.read()
    content = re.sub(r'_sta\.config\(channel=\d+\)',
                     f'_sta.config(channel={cfg["channel"]})', content)
    with open(path, "w") as f:
        f.write(content)
    print(f"  Channel {cfg['channel']} injected → {path}")


def inject_rpi_ip(cfg):
    path = "rpi/udp_comm.py"
    with open(path) as f:
        content = f.read()
    content = re.sub(r'ESP32_IP\s*=\s*".*?"',
                     f'ESP32_IP   = "{cfg["rpi"]["esp32_ip"]}"', content)
    with open(path, "w") as f:
        f.write(content)
    print(f"  ESP32 IP {cfg['rpi']['esp32_ip']} injected → {path}")


def mpremote_upload(com, *file_pairs):
    """Upload files to a board. file_pairs: (local_path, remote_path)"""
    for local, remote in file_pairs:
        cmd = ["python", "-m", "mpremote", "connect", com, "cp", local, remote]
        print(f"  Uploading {local} → {com}:{remote}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr.strip()}")
        else:
            print(f"  OK")


def upload_all(cfg):
    nodes = cfg["nodes"]

    print("\n[UPLOAD] Host →", nodes["host"]["com"])
    mpremote_upload(nodes["host"]["com"],
        ("Nodes/host/main.py",                   ":main.py"),
        ("Nodes/host/host_config.json",           ":config.json"),
        ("Nodes/host/host_peer_file.json",        ":peer_file.json"),
        ("ESP-Now_Comm_Packet/smart_esp_comm.py", ":smart_esp_comm.py"),
    )

    print("\n[UPLOAD] camera_bridge →", nodes["camera_bridge"]["com"])
    mpremote_upload(nodes["camera_bridge"]["com"],
        ("esp32_rpi_bridge/main.py",         ":main.py"),
        ("esp32_rpi_bridge/camera_mesh.py",  ":camera_mesh.py"),
        ("esp32_rpi_bridge/config.json",     ":config.json"),
        ("esp32_rpi_bridge/peer_file.json",  ":peer_file.json"),
        ("ESP-Now_Comm_Packet/smart_esp_comm.py", ":smart_esp_comm.py"),
    )

    print("\n[UPLOAD] leak_sensor →", nodes["leak_sensor"]["com"])
    mpremote_upload(nodes["leak_sensor"]["com"],
        ("leak_sensor/main.py",              ":main.py"),
        ("leak_sensor/config.json",          ":config.json"),
        ("leak_sensor/peer_file.json",       ":peer_file.json"),
        ("ESP-Now_Comm_Packet/smart_esp_comm.py", ":smart_esp_comm.py"),
    )


def main():
    print(f"[SETUP] Loading {CONFIG_FILE}...")
    cfg = load_config()
    nodes = cfg["nodes"]

    print("\n[STEP 1] Generating peer files...")
    write_peer_file("Nodes/host/host_peer_file.json",
                    generate_peer_file("host", nodes))
    write_peer_file("esp32_rpi_bridge/peer_file.json",
                    generate_peer_file("camera_bridge", nodes))
    write_peer_file("leak_sensor/peer_file.json",
                    generate_peer_file("leak_sensor", nodes))

    print("\n[STEP 2] Injecting WiFi credentials...")
    inject_wifi(cfg)

    print("\n[STEP 3] Injecting AP channel...")
    inject_channel(cfg)

    print("\n[STEP 4] Injecting RPi ESP32 IP...")
    inject_rpi_ip(cfg)

    print("\n[STEP 5] Uploading to boards...")
    answer = input("Upload to boards now? (y/n): ").strip().lower()
    if answer == "y":
        upload_all(cfg)
    else:
        print("Skipped upload. Run mpremote manually or re-run setup.py.")

    print("\n[SETUP] Done.")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
