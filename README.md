# ESP_SmartHome

The ESP_SmartHome project contains software for a simple IoT sensor network for smart home monitoring. It is written in Python, and runs on MicroPython, a Python implementation for microcontrollers. 

Materials needed:
* A host computer, such as a Raspberry Pi
* One or more Featherboard V2 (preferably multiple)
  - Other boards might work with some configuration
* One or more of the following sensors: 
  - SGP41 Air Quality Sensor Module
  - A liquid conductivity sensor
  - The Raspberry Pi Camera Module
* A way to create electrical connections between components (Depending on the materials you have, this may be wires and a breadboard, solder and printed circuit boards, or some other setup I'm not aware of)

## Installation

### Host computer

Install python on your host computer. Then run 

### Featherboard V2

Flash the Featherboard V2 with micropython. Update node_a_micropython/config.py to have the MAC address of the host computer. Then load all the files from the node_a_micropython directory to the root filesystem of the Featherboard. 



## Organization

 * ESP-Now_Comm