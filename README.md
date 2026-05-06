# ESP_SmartHome

The ESP_SmartHome project contains software for a simple IoT sensor network for smart home monitoring. It is written in Python, and runs on MicroPython, a Python implementation for microcontrollers. 

Materials needed:
* A host computer, such as a Raspberry Pi
* One or more Featherboard V2 (preferably multiple)
  - Other boards might work with some configuration
* One or more of the following sensors: 
  - SGP41 Air Quality Sensor Module
  - A liquid conductivity sensor
  - The Raspberry Pi Camera Module (with a Raspberry Pi)
  - DHT20 I2C Temperature and Humidity Sensor
  - BH1750 Ambient Light Sensor
  - A PIR (passive infrared) Sensor
  - MAX17048 LiPo Fuel Gauge Sensor
* A way to create electrical connections between components (Depending on the materials you have, this may be wires and a breadboard, solder and printed circuit boards, or some other setup I'm not aware of)

## Installation

### Host computer

Install Python on your host computer, and install mpremote by running `pip install --user mpremote`. 

### Raspberry Pi

Install Python and mpremote onto your Raspberry Pi, if you haven't already done so as the host. Connect the Raspberry Pi Camera Module if you intend to use the door monitoring functionality of this project. See Door_Monitor/rpi/README.md for more details. 

### Featherboard V2

Flash each featherboard V2 with micropython, then connect the hardware, and for each board, follow the instructions in the subdirectory of Nodes corresponding to the purpose of the board. 

To set the network up automatically, edit network_config.json with your network and node details, and run `python setup.py` to deploy files to the nodes autoamtically (see MESH_TESTING.md for more details). Alternatively, for each node, upload the subdirectory of Nodes corresponding to the purpose of the node, along with ESP-Now_Comm_Packet/smart_esp_comm.py as smart_esp_comm.py (see PERSONAL_TESTING.md for more details). 

## Organization

 * ESP-Now_Comm