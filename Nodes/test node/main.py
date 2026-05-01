import smart_esp_comm as sh
from machine import Pin
from neopixel import NeoPixel
import time

# ── Hardware ──────────────────────────────────────────────────────────────────

neoPWR = Pin(2,Pin.OUT)
neoPWR.value(1)
neoPix = NeoPixel(Pin(0,Pin.OUT),1)
neoPix[0] = (255,0,0)
neoPix.write()

COLORS = [
    (255, 0,   0),   # Red
    (0,   255, 0),   # Green
    (0,   0,   255), # Blue
]
color_index = 0

# ── Setup ─────────────────────────────────────────────────────────────────────


def board_setup():
    neoPix[0] = (0, 0, 0)
    neoPix.write()
    print("[BOARD] NeoPixel cleared.")

def change_led():
    global color_index
    color = COLORS[color_index]
    neoPix[0] = color
    neoPix.write()
    print(f"[LED] Color set to {['Red','Green','Blue'][color_index]}")
    color_index = (color_index + 1) % len(COLORS)

# ── Boot ──────────────────────────────────────────────────────────────────────

sh.boot()
board_setup()

# ── Main Loop ─────────────────────────────────────────────────────────────────

change_led()
time.sleep(3)
change_led()
time.sleep(3)
change_led()
time.sleep(3)


while True:
    sh.poll_serial()
    
    if sh.check_request_flag() == True:
        print("[MAIN] Action request received — toggling LED...")
        change_led()
