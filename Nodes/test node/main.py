import smart_esp_comm as sh
 
sh.boot()
 
while True:
    sh.poll_serial()
