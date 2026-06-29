# ESP32 Laser Tag System

A full-stack infrared laser tag system built from simulation to hardware deployment on ESP32-S3.
Developed as a course project at Oklahoma State University, evolved through multiple iterations
into a networked, server-authoritative multiplayer game.

## System Architecture

- **Firmware**: ESP32-S3 C++ client handling IR transmit/receive, WiFi, and TCP communication
- **Server**: Python TCP server managing game state, hit validation, respawn timers, and scoring
- **Simulation**: Python prototype used to validate game logic before hardware deployment

## Features

- Server-authoritative damage model (eliminates double-damage race conditions)
- Team-based friendly fire detection via IR address encoding
- Multithreaded TCP server supporting up to 20 concurrent ESP32 clients
- JSON protocol over TCP for all client-server communication
- Heartbeat timeout detection with automatic player cleanup
- Graceful SIGINT shutdown with final scoreboard display
- 5-second respawn with server-pushed RESPAWN message
- Hold-to-reload vs tap-to-shoot trigger logic on embedded client

## Hardware Requirements

- ESP32-S3 Feather (STEMMA QT)
- IR LED 940nm on GPIO 18 with 100Ω resistor
- TSOP38238 IR receiver on GPIO 16
- Trigger button on GPIO 9

## Dependencies

**Firmware (Arduino):**
- IRremote
- ArduinoJson
- WiFi (built-in ESP32)

**Server:**
Python 3.8+

No external dependencies (stdlib only)

**Simulation:**
pip install matplotlib

## Setup

### Server
```bash
python server/laser_server.py
```

### Firmware
1. Open `firmware/laser_tag_FINAL_COMPLETE.ino` in Arduino IDE
2. Set your values at the top of the file:
```cpp
const char* WIFI_SSID = "your_network";
const char* WIFI_PASSWORD = "your_password";
const char* SERVER_IP = "your_server_ip";
String playerID = "P1";  // Change per device
int teamID = 1;          // 1 or 2
```
3. Flash to ESP32-S3

## Project Structure

laser-tag-esp32/

├── simulation/

│   └── BasicLaserTag_Sim.py      # Python OOP simulation with score visualization

├── server/

│   ├── laser_server.py           # Final production server

│   ├── laser_server_v2.py        # Intermediate version with console commands

│   └── LaserTag_Server.py        # Initial hardware server

├── firmware/

│   ├── laser_tag_FINAL_COMPLETE.ino   # Final ESP32-S3 firmware

│   └── LaserTag.cpp                   # Initial firmware iteration

├── docs/

│   └── System_Overview_Document.txt

└── archive/

└── EXCode_server.py          # Early prototype server


## Protocol

All messages are newline-delimited JSON over TCP port 5000.

| Message | Direction | Description |
|---|---|---|
| `INIT` | Client → Server | Player registration with team ID |
| `INIT_OK` | Server → Client | Confirmation with player count |
| `HIT` | Client → Server | Report incoming IR hit |
| `HIT_OK` | Server → Client | Hit validated |
| `HIT_RECEIVED` | Server → Client | Notify target of damage and new health |
| `STATE_UPDATE` | Client → Server | Heartbeat with current player state |
| `REQUEST_RELOAD` | Client → Server | Request ammo refill |
| `RELOAD` | Server → Client | Ammo restored |
| `RESPAWN` | Server → Client | Player restored after elimination |

## Game Rules

- 100 HP per player, 10 damage per hit
- 10-round magazine, hold trigger 3 seconds to reload
- 5-second respawn timer
- Friendly fire disabled (team encoded in IR address)
- +100 points per elimination

## Author

Alex Malakar
