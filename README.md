# RNS Interface ESP-NOW

ESP32-based wireless interface for [Reticulum Network Stack](https://github.com/markqvist/Reticulum) using ESP-NOW.

## Current Status ⚠️

This code is under active development and not yet ready for general use.

## 🤔 Why?

[ESP-NOW](https://github.com/espressif/esp-now) provides an efficient transport layer for Reticulum networks:

- No infrastructure required - direct peer-to-peer
- High bandwidth (**1-2Mbps**)
- Long range capability with ESP32
- Low latency (<4ms)
- Built into most ESP32 (~$5)
- Simple protocol
- Zero configuration

## 🔧 Components

Framing is done using [`HDLC`](https://en.wikipedia.org/wiki/High-Level_Data_Link_Control) from/to Reticulum.

### UART Processing
- [Interfaces]([Simple protocol](https://github.com/markqvist/Reticulum/blob/master/RNS/Interfaces/SerialInterface.py) with Reticulum daemon (`rnsd`)
- Configurable pins and baud rate
- Handles frame buffering and delimiting

### ESP-NOW Transport
- WiFi station mode (no access point required - "ad hoc")
- Group broadcast approach (think `VLAN`)
- Long range mode enabled (needs testing)
- Power management optimized (also needs testing)
- Channel scanning for automatic peer discovery

## 🔄 Data Flow

### UART to ESP-NOW
1. Buffer serial data
2. Process complete frames
3. Broadcast via ESP-NOW

### ESP-NOW to UART
1. Receive broadcasts
2. Handle special frames (ping/probe)
3. Forward regular frames to UART

## 🔍 Network Discovery

### Channel Selection
1. Scan preferred channels first
2. Send probes, count responses
3. Select best channel
4. Eventually fall back to default

### Special Frames
- `GROUP_ID` prefixed:
	- `PING`: Connectivity test
	- `PROBE`: Channel scanning
	- `ACK`: Probe response

## 📡 Hardware Setup

Minimum requirements:
- ESP32 with [MicroPython](https://micropython.org/)
- Secondary UART (USB)
- Peripherals: LED, Button

## License

MIT License