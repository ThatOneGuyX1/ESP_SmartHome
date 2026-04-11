import smart_esp_comm as sh

sh.boot()
        
    # Temporary test commands — remove before deploying
sh.handle_serial_command("ADD living_room AA:BB:CC:DD:EE:FF 1 3 host")
sh.handle_serial_command("LIST")
sh.handle_serial_command("SYNC")
while (1):
    sh.poll_serial()

