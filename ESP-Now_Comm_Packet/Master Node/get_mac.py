import network
sta = network.WLAN(network.STA_IF)
sta.active(True)
print(':'.join('%02X' % b for b in sta.config('mac')))
