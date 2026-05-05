# main.py
# motion_1 node: MPU6050 + MAX17048 + ESP-NOW

import time
from machine import Pin, I2C

import config
import smart_esp_comm as sh
from mpu6050 import MPU6050
from max17048_driver import MAX17048


BOOT_MS = time.ticks_ms()

sh.boot()

HOST_MAC = sh.mac_bytes(sh.PEER_DICT["host"]["mac"])


# ── I2C setup ─────────────────────────────────────────────
i2c = I2C(
    0,
    scl=Pin(config.I2C_SCL_PIN),
    sda=Pin(config.I2C_SDA_PIN),
    freq=config.I2C_FREQ
)

if config.PRINT_I2C_SCAN:
    print("[I2C] Scan:", [hex(addr) for addr in i2c.scan()])


# ── Sensor setup ──────────────────────────────────────────
mpu = MPU6050(i2c, address=config.MPU6050_ADDR)
battery = MAX17048(i2c, address=config.MAX17048_ADDR)

print("[NODE] motion_1 ready")


# ── Red LED setup ─────────────────────────────────────────
red_led = Pin(config.RED_LED_PIN, Pin.OUT)


def set_red_led(on):
    if config.RED_LED_ACTIVE_HIGH:
        red_led.value(1 if on else 0)
    else:
        red_led.value(0 if on else 1)


set_red_led(False)


# ── Calibration ───────────────────────────────────────────
def calibrate_mpu():
    sx = 0
    sy = 0
    sz = 0

    print("[CAL] Calibrating MPU6050. Keep sensor still...")

    for _ in range(config.CALIBRATION_SAMPLES):
        ax, ay, az = mpu.read_accel_ms2()

        sx += ax
        sy += ay
        sz += az

        time.sleep_ms(config.CALIBRATION_DELAY_MS)

    bx = sx / config.CALIBRATION_SAMPLES
    by = sy / config.CALIBRATION_SAMPLES
    bz = sz / config.CALIBRATION_SAMPLES

    print("[CAL] Baseline:", bx, by, bz)

    return bx, by, bz


BASE_X, BASE_Y, BASE_Z = calibrate_mpu()


# ── Health packet ─────────────────────────────────────────
def make_battery_health():
    soc = battery.read_soc()

    # Golden smart_esp_comm.py health packet carries:
    # temp, battery, uptime.
    return {
        "temp": int(mpu.read_temp_c()),
        "battery": int(soc),
        "uptime": time.ticks_diff(time.ticks_ms(), BOOT_MS) // 1000
    }


# ── Motion reading ────────────────────────────────────────
def read_motion_sample():
    ax, ay, az = mpu.read_accel_ms2()

    dx = abs(ax - BASE_X)
    dy = abs(ay - BASE_Y)
    dz = abs(az - BASE_Z)

    m = 1 if (
        dx >= config.THRESHOLD_X or
        dy >= config.THRESHOLD_Y or
        dz >= config.THRESHOLD_Z
    ) else 0

    set_red_led(m == 1)

    if config.PRINT_MOTION_DEBUG:
        print(
            "[MPU]",
            "x:", round(ax, 2),
            "y:", round(ay, 2),
            "z:", round(az, 2),
            "dx:", round(dx, 2),
            "dy:", round(dy, 2),
            "dz:", round(dz, 2),
            "M:", m,
            "LED:", "ON" if m else "OFF"
        )

    return ax, ay, az, m


def make_motion_message(ax, ay, az, m):
    # Keep under golden packet 32-byte message limit.
    # Example: X:0.2,Y:-0.1,Z:9.8,M:1
    msg = "X:{:.1f},Y:{:.1f},Z:{:.1f},M:{}".format(ax, ay, az, m)

    if len(msg) > sh.MAX_MSG_BYTES:
        msg = msg[:sh.MAX_MSG_BYTES]

    return msg.encode("utf-8")


# ── Main loop ─────────────────────────────────────────────
while True:
    ax, ay, az, m = read_motion_sample()

    msg = make_motion_message(ax, ay, az, m)
    health = make_battery_health()

    packet = sh.create_msg_packet(
        dest_mac=HOST_MAC,
        action=sh.ACT_REPORT_HOME,
        message=msg,
        health=health,
        trail=[]
    )

    sh.espnow_send(HOST_MAC, packet)

    if config.PRINT_TX_DEBUG:
        print("[TX]", msg, health)

    time.sleep_ms(config.REPORT_INTERVAL_MS)