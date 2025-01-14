# Bar-Blinker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

A Raspberry Pi-based controller for WLED LED strips with GPIO input triggering and web configuration capabilities. The system monitors contact closure events through GPIO to control LED strip states via the WLED API.

## Technical Specifications

### Threading Architecture
- Multi-threaded design with three primary threads:
  1. Main Thread (Flask Web Server)
     - Handles web interface requests
     - Configuration management
     - HTTP endpoints for simulation
     - Template rendering
  
  2. Hardware Monitoring Thread
     - Continuous GPIO state monitoring
     - Debounce implementation
     - Contact closure duration tracking
     - State transition management
  
  3. Connection Management Thread
     - Background WLED connectivity
     - Automatic reconnection logic
     - Exponential backoff implementation
     - Connection state monitoring

### Input Processing
- Contact closure detection via GPIO
- Configurable pull-up/pull-down resistance
- Software-based debounce implementation

### State Control Logic
- Short contact (< 6s):
  - Initiates green notification sequence
  - 30-second timeout (configurable)
  - Subsequent triggers ignored during active sequence
  - Automatic state restoration

- Sustained contact (≥ 6s):
  - Triggers red alert sequence
  - Maintains state during contact closure
  - Overrides current sequence
  - Returns to default on release

- Idle state:
  - Maintains constant white illumination
  - Automatic restoration post-sequence

### Web Interface Specifications
- HTTP server on port 5000
- Real-time parameter adjustment
- Input simulation capability
- System status monitoring
- Configuration management

### State Machine Logic
- Contact Closure States:
  - Idle: No input detected
  - Short Press: < 6 seconds (configurable)
  - Long Press: ≥ 6 seconds (configurable)
  - Debounce: Input stabilization period

- LED States:
  - Default: Constant white (RGB: 255,255,255)
  - Notification: Green blinking (RGB: 0,255,0)
  - Alert: Red blinking (RGB: 255,0,0)
  - Off: Transitional state (RGB: 0,0,0)

### HTTP API Endpoints
- Root (/): Configuration interface
- /update_config (POST): Parameter updates
- /simulate_press (POST): Input simulation
  - Parameters:
    - press_type: "short" or "long"

### System Architecture
- Multi-threaded operation:
  - Main thread: Web server, configuration
  - GPIO thread: Input monitoring
  - Network thread: WLED communication
- Thread-safe state management
- Resource locking implementation
- Graceful shutdown handling

## Requirements

### Hardware
- Raspberry Pi (any model with GPIO)
- Input device specifications:
  - Operating voltage: 3.3V
  - Maximum current: 8mA per GPIO
  - Contact resistance: < 100Ω
- WLED-compatible controller (ESP8266/ESP32)
- LED strip with appropriate power supply

### Software Dependencies
- Raspberry Pi OS (Buster or newer)
- Python 3.6+
- Required packages:
```bash
flask>=2.0.0
requests>=2.25.1
RPi.GPIO>=0.7.0
```

## Installation

### System Setup
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip git
```

### Application Installation
```bash
git clone https://github.com/morroware/Bar-Blinker.git
cd Bar-Blinker
pip3 install -r requirements.txt
```

### Service Configuration
```bash
cp config/blinker-configs.ini.example blinker-configs.ini
sudo cp systemd/bar-blinker.service /etc/systemd/system/
sudo systemctl enable bar-blinker
sudo systemctl start bar-blinker
```

## Hardware Configuration

### GPIO Connection
```
Input Device Connection:
GPIO 18 ─── Input Device ─── GND
```

Configuration parameters:
- GPIO pin: 18 (default, configurable)
- Internal pull-up enabled
- Active-low logic
- Software debounce implementation

### Network Configuration
- WLED controller requirements:
  - Static IP recommended
  - Network accessibility from Raspberry Pi
  - Same subnet placement

## Configuration Parameters

### Logging System
- File Location: ~/wled_button.log (configurable)
- Rotation Policy:
  - Maximum Size: 1MB per file
  - Backup Count: 5 files
  - Format: Timestamp - Level - Message
- Console Output: Simultaneous logging
- Level: INFO (default)

### Connection Management
- Automatic Reconnection:
  - Exponential backoff algorithm
  - Maximum delay: 60 seconds
  - Jitter: ±10% of delay
  - Continuous retry mechanism

### WLED Communication
- Protocol: HTTP/JSON
- Endpoints:
  - /json/info: Device information
  - /json/state: State control
- State Parameters:
  - on: Boolean power state
  - bri: Brightness (0-255)
  - transition: Effect duration (ms)
  - seg: Array of segment configurations
    - id: Segment identifier
    - col: RGB color array
    - fx: Effect index
    - sx: Effect speed
    - ix: Effect intensity

### Primary Configuration (blinker-configs.ini)
```ini
[BLINKER]
BUTTON_PIN = 18              # GPIO input pin
WLED_IP = "192.168.6.12"     # WLED controller address
LONG_PRESS_THRESHOLD = 6.0    # Sustained contact threshold (seconds)
SHORT_FLASH_DURATION = 30.0   # Notification sequence duration
FLASH_INTERVAL = 0.5         # State change interval
FLASH_BRIGHTNESS = 255       # LED intensity (0-255)
TRANSITION_TIME = 0.0        # Color transition duration
LOG_FILE = "~/wled_button.log"
MAX_RETRIES = 3
RETRY_DELAY = 1
```

## System Management

### Service Control
```bash
sudo systemctl status bar-blinker    # Status verification
sudo systemctl restart bar-blinker   # Service restart
journalctl -u bar-blinker -f        # Log monitoring
```

### Error Resolution
1. Input Malfunction
   - Verify GPIO connections
   - Check input device functionality
   - Review system logs

2. LED Control Issues
   - Verify WLED IP configuration
   - Test network connectivity
   - Confirm WLED controller power

3. Interface Access Problems
   - Check service status
   - Verify network configuration
   - Review HTTP server logs

## External Dependencies
- WLED Firmware
- Flask Framework
- Raspberry Pi GPIO Library
## External Dependencies
- WLED Firmware
- Flask Framework
- Raspberry Pi GPIO Library
