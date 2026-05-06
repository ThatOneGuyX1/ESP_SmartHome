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

### GUI

To use the GUI, you will need to designate a node as the host gateway and upload the files in host_gateway to that node. Connect this node to the host through a serial connection. Then on the host, create a virtual environment in the GUI directory, and install the requirements in GUI/requirements.txt by running `pip install -r requirements.txt`. 

Once both the host and host gateway are set up, you can run the GUI by running `python main.py` within the virtual environment.

## Organization

  * Archive_FILES: Files that are no longer in use, but may be useful for reference or future work.
  * ESP-Now_Comm_Packet: Contains the ESP-Now communication packet structure and utility functions. 
  * esp32_rpi_bridge: Contains files for bridging between the ESP32 and a Raspberry Pi with a camera module.
  * GUI: Contains the graphical user interface for monitoring the network. 
  * host_gateway: Contains files for the host gateway node, which communicates to the host and is needed to run the GUI on the host. 
  * leak_sensor: Contains files for the leak sensor node. 
  * node_a_firmware: Contains files for the implementation of the node firmware in C. 
  * Nodes: Contains subdirectories for most of the possible kinds of nodes. 
  * test_listener: Contains files for the implementation of the listener node in C.
  * test_listener_micropython: Contains files for the implementation of the listener node in Python (micropython).
