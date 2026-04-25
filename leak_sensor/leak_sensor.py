from machine import ADC, Pin
import time

# Feather V2 analog pins: A0=26, A1=25, A2=34, A3=39, A4=36, A5=4
adc = ADC(Pin(26))          # change pin number to match where you plugged in
adc.atten(ADC.ATTN_11DB)    # full 0-3.3V range

LEAK_THRESHOLD = 1000       # tune this — dry reads low, wet reads higher

while True:
    val = adc.read()        # 0-4095
    if val > LEAK_THRESHOLD:
        print(f"LEAK DETECTED — ADC={val}")
    else:
        print(f"Dry — ADC={val}")
    time.sleep(0.5)
