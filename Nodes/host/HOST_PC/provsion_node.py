"""
provision_node.py
─────────────────
Reads nodes_manifest.json and provisions every node automatically.
No human input required.

Usage:
    python provision_node.py
    python provision_node.py my_manifest.json

Dependencies:
    pip install pyserial
    mpremote (MicroPython toolchain)
"""

import json
import subprocess
import time
import serial
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MANIFEST = "nodes_manifest.json"
BAUD             = 115200
TIMEOUT_S        = 2

PROVISION_FILES  = [
    "smart_esp_comm.py",
    "main.py",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def generate_node_config(name, hop, node_id):
    config = {"name": name, "hop": hop, "id": node_id}
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)
    print(f"[PROVISION] Generated config.json: {config}")


def generate_empty_peer_file():
    with open("peer_file.json", "w") as f:
        json.dump({"peers": {}}, f)
    print("[PROVISION] Generated empty peer_file.json")


def push_files(files, node_port=None):
    base = ["mpremote"]
    if node_port:
        base += ["connect", node_port]

    for fp in files:
        if not os.path.exists(fp):
            print(f"[ERROR] Missing: {fp}")
            continue
        dest = ":" + os.path.basename(fp)
        cmd = base + ["cp", fp, dest]
        print(f"[FLASH] {' '.join(cmd)}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[ERROR] {r.stderr.strip()}")
        else:
            print(f"[FLASH] {fp} -> {dest}")

    subprocess.run(base + ["reset"], capture_output=True, text=True)
    print("[FLASH] Node reset.")


def send_command(port, command):
    print(f"[HOST] >> {command}")
    with serial.Serial(port, BAUD, timeout=TIMEOUT_S) as ser:
        time.sleep(0.5)
        ser.write((command + "\n").encode())
        time.sleep(1.0)
        while ser.in_waiting:
            line = ser.readline().decode(errors="replace").strip()
            if line:
                print(f"[HOST] << {line}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    manifest_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MANIFEST

    if not os.path.exists(manifest_path):
        print(f"[ERROR] Manifest not found: {manifest_path}")
        sys.exit(1)

    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    host_port = manifest["host_port"]
    nodes     = manifest["nodes"]

    print("=" * 50)
    print("  ESP Smart Home -- Auto Provisioning")
    print(f"  Host     : {host_port}")
    print(f"  Nodes    : {len(nodes)}")
    print("=" * 50)

    for i, node in enumerate(nodes, 1):
        name      = node["name"]
        mac       = node["mac"]
        hop       = node["hop"]
        node_id   = node["id"]
        neighbors = node["neighbors"]
        node_port = node.get("node_port")
        do_flash  = node.get("flash", True)

        print(f"\n{'─' * 50}")
        print(f"  [{i}/{len(nodes)}] {name}  |  {mac}  |  hop {hop}")
        print(f"{'─' * 50}")

        # Phase 1: Flash
        if do_flash:
            print("[Phase 1] Flashing...")
            generate_node_config(name, hop, node_id)
            generate_empty_peer_file()
            push_files(
                ["config.json", "peer_file.json"] + PROVISION_FILES,
                node_port
            )
            time.sleep(3)
        else:
            print("[Phase 1] Skipped (flash: false)")

        # Phase 2: Register on host
        print("[Phase 2] Registering on host...")
        send_command(host_port, f"ADD {name} {mac} {hop} {node_id} {neighbors}")

    # Phase 3: Single sync after all nodes registered
    print(f"\n{'─' * 50}")
    print("[Phase 3] Syncing mesh...")
    send_command(host_port, "SYNC")

    print(f"\n[DONE] {len(nodes)} node(s) provisioned. Mesh synced.")


if __name__ == "__main__":
    main()