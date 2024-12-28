# 📡 RNS Interface ESP-NOW 

ESP32-based wireless interface for [Reticulum Network Stack](https://github.com/markqvist/Reticulum) using ESP-NOW.

## ⚠️ Current Status

This code is functional and ready for testing. Core features are implemented:

- 🎯 HDLC framing of serial data
- 📻 ESP-NOW transport with packet fragmentation and reassembly
- 🔧 Configuration via `AT` commands
- 💾 Persistent configuration storage

## 🤔 Why?

[ESP-NOW](https://github.com/espressif/esp-now) provides a hardware interface for Reticulum networks:

- 🏗️ No infrastructure required - direct peer-to-peer
- 🚀 High bandwidth (up to 1Mbps) 
- ⚡ Low latency (<4ms)
- 💰 Built into most ESP32 (~$5)
- 🧩 Works with `SerialInterface`

## 🐍 Why MicroPython?

MicroPython provides ideal characteristics for RNS ESP-NOW interface development:

- Interactive REPL and runtime execution enables fast prototyping and testing
- Directly aligns with Reticulum's Python codebase, allowing shared patterns
- AsyncIO enables efficient concurrent I/O handling
- Clear, readable code structure

### 📸 Flashing

First steps first:

* MicroPython needs to be [flashed](https://docs.micropython.org/en/latest/esp32/tutorial/intro.html) to the ESP32
* The [mpremote](https://github.com/micropython/micropython/tree/master/tools/mpremote) tool is recommended for device management and file operations.

## 🌐 System Design

The system utilizes an event-driven architecture with components communicating through a lightweight event bus.

### 📍 Core Components

```mermaid
classDiagram
    class EventBus {
        -dict listeners
        +add_listener(event: str, listener: func)
        +remove_listener(event: str, listener: func) 
        +emit(event: str, data: any)
    }

    class RNSNOW {
        -Config config
        -Logger log
        -HDLCProcessor hdlc
        -Fragmentor fragmentor
        -Hardware hw
        -UART uart
        -EventBus event_bus
        -ATCommands at
        +process_uart()
        +process_espnow()
    }

    class HDLCProcessor {
        -Logger log
        -bytearray rx_buffer
        -bool in_frame
        -bool escape
        +frame_data(data: bytes)
        +process_byte(byte: int)
    }

    class Fragmentor {
        -Logger log
        -dict _reassembly
        +fragment_data(data: bytes)
        +process_fragment(fragment: bytes)
    }

    class Hardware {
        -Pin led
        -Pin btn1
        -EventBus event_bus
        +blink_led(times: int)
        +check_buttons()
    }

    class ATCommands {
        -Config config
        -EventBus event_bus
        -UART uart
        +process_byte(byte: int)
        +process_command(cmd: str)
    }

    RNSNOW --> EventBus
    RNSNOW --> HDLCProcessor
    RNSNOW --> Fragmentor
    RNSNOW --> Hardware
    RNSNOW --> ATCommands
    Hardware --> EventBus
    ATCommands --> EventBus
```

### 🎬 Events

The system responds to several core events:

- **Control Events**: Channel changes (`ch_ch`), baudrate changes (`ch_bd`)
- **Hardware Events**: Button presses, LED signals
- **Network Events**: ESP-NOW transmission/reception, ping requests/responses
- **Configuration Events**: Settings changes via AT commands

### 🔌 UART Processing

- Single UART interface for both data and AT commands
- Configurable pins and baud rate
- `AT` command set for configuration
- HDLC frame processing for RNS packets

### 📻 ESP-NOW Transport 

- WiFi station mode (no AP needed)
- Group broadcast approach
- Long range mode support
- Packet fragmentation for RNS MTU compliance

## 🔄 Data Flow

```mermaid
sequenceDiagram
    participant RNS as RNS Daemon
    participant UART as UART Handler
    participant HDLC as HDLC Processor
    participant FRAG as Fragmentor
    participant NOW as ESP-NOW
    
    RNS->>UART: Serial Data
    UART->>HDLC: Process Bytes
    HDLC->>FRAG: Complete Frame
    FRAG->>NOW: Fragments
    NOW-->>FRAG: Fragments
    FRAG-->>HDLC: Complete Frame
    HDLC-->>UART: Frame Data
    UART-->>RNS: Serial Data
```

## 👾 Hardware

The interface uses a minimal hardware configuration:

```mermaid
graph TD
    subgraph "ESP32 Development Board"
        CPU[ESP32 MCU]
        
        subgraph "Peripherals"
            LED[LED - Pin 10]
            BTN1[Button1 - Pin 37]
        end
        
        subgraph "Communications"
            UART[UART1 - Data + AT]
            WIFI[WiFi/ESP-NOW]
        end
    end
    
    subgraph "Connections"
        RNS[RNS Daemon]
        AIR[Wireless Medium]
    end
    
    CPU --> LED
    BTN1 --> CPU
    CPU <--> UART
    CPU <--> WIFI
    
    UART <--> RNS
    WIFI <--> AIR
    
    classDef peripheral fill:#f9f,stroke:#333
    classDef comm fill:#bbf,stroke:#333
    class LED,BTN1 peripheral
    class UART,WIFI comm
```

## 📡 Configuration

The device can be configured via AT commands:

- `AT` - Test command
- `ATI` - Show device info  
- `AT&F` - Factory reset
- `AT&V` - View config
- `AT&W` - Write config
- `AT+DESC=text` - Set description
- `AT+BAUD=rate` - Set baudrate
- `AT+CHAN=n` - Set WiFi channel (1-14)
- `AT+MAC=xxxxxxxxxxxx` - Set target MAC
- `AT+LOG=n` - Set log level (0-4)
- `AT+PROTO=type` - Set protocol (default/lr)
- `AT+PINS=name,val - Configure pin (name: led/button1/button2/tx/rx, val: pin number or NONE)`
- `AT+RESET` - Reset device

Settings are stored in `config.json` and persist across reboots.

## 🎯 Development Target

While this interface should work on any ESP32-based platform, current development and testing is being done exclusively on ESP32-S3 based boards. Development is ongoing and testing with other ESP32 platforms will follow as the project matures.

## 🤝 Contributing

Contributions welcome! Please:
- 🐛 Report bugs
- 💡 Suggest features  
- 🔧 Submit pull requests
- 📢 Share your experiences

## 🎫 Sponsor

This work is supported by the [Critical Decentralisation Cluster (CDC)](https://decentral.community/) - thank you very much!

## 📄 License

MIT License - See LICENSE file for full details.

## 🖇 References

- https://github.com/espressif/esp-now
- https://docs.espressif.com/projects/esp-faq/en/latest/application-solution/esp-now.html
- https://github.com/espressif/esp-now/blob/master/User_Guide.md
- https://docs.micropython.org/en/latest/library/espnow.html
- https://github.com/micropython/micropython-lib/blob/master/micropython/aioespnow/aioespnow.py