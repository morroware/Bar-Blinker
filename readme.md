# Bar-Blinker RGBW

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

A Raspberry Pi-based controller for RGBW LED strips using WLED, featuring GPIO input triggering and web-based configuration. The system monitors contact closure events to control LED states and effects via the WLED API with full RGBW color support.

## Technical Specifications

### RGBW Color Control
- Full RGBW channel support (Red, Green, Blue, White)
- Dedicated white channel utilization (0,0,0,255)
- Color sequences:
  - Short press: Blue/White toggle (0,0,255,0 ↔ 0,0,0,255)
  - Long press: Red/Off toggle (255,0,0,0 ↔ 0,0,0,0)
- Built-in WLED effect support
- Configurable transition timings

### Input Processing
- Contact closure detection via GPIO
- Compatible input devices:
  - Push buttons
  - Relays
  - Solid-state relays
  - Open collector outputs
  - Any contact closure mechanism
- Software debounce implementation
- Configurable pull-up resistance

### State Machine Logic
- Short contact (<3s default):
  - Triggers blue/white sequence
  - Configurable timeout period
  - Auto-restoration to default state
  - Debounced input handling

- Long contact (≥3s default):
  - Activates red alert sequence
  - Maintains state during closure
  - Priority override capability
  - Auto-restoration on release

### System Architecture
- Multi-threaded operation:
  1. Main Thread
     - Web server (Flask)
     - Configuration management
     - Rate limiting
     - Authentication handling
  
  2. Hardware Thread
     - GPIO state monitoring
     - Debounce processing
     - LED state control
     - Health monitoring
  
  3. Connection Thread
     - WLED communication
     - Auto-reconnection
     - State caching
     - Effect management

### Health Monitoring
- System status tracking
- Connection state monitoring
- Error logging and reporting
- Automatic recovery mechanisms
- Web-based health dashboard

## Requirements

### Hardware
- Raspberry Pi (any model with GPIO)
- Input device specifications:
  - Voltage: 3.3V compatible
  - Current: 8mA max per GPIO
  - Contact resistance: < 100Ω
- WLED-compatible controller
  - ESP8266/ESP32 based
  - RGBW strip support
  - Network connectivity
- RGBW LED strip
  - Common anode/cathode
  - Proper power supply

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

### System Preparation
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

## Configuration Parameters

### Primary Configuration (blinker-configs.ini)
```ini
[BLINKER]
BUTTON_PIN = 18                  # GPIO input pin
WLED_IP = "192.168.1.15"        # WLED controller address
LONG_PRESS_THRESHOLD = 3.0       # Sustained contact threshold (seconds)
SHORT_FLASH_DURATION = 5.0       # Sequence duration
FLASH_INTERVAL = 0.5            # State change interval
FLASH_BRIGHTNESS = 255          # LED intensity (0-255)
DEFAULT_MODE = "white"          # "white" or "effect"
DEFAULT_EFFECT_INDEX = 162      # WLED effect number
DEFAULT_EFFECT_SPEED = 128      # Effect speed (0-255)
DEFAULT_EFFECT_INTENSITY = 128  # Effect intensity (0-255)
WLED_USERNAME = null            # Optional auth
WLED_PASSWORD = null            # Optional auth
```

## Web Interface

### Features
- Real-time control panel
- Configuration management
- Health monitoring
- Effect selection
- Color control
- Authentication support

### Endpoints
- / : Main interface
- /update_config : Configuration updates
- /simulate_press : Input simulation
- /health : System status

### Rate Limiting
- Configurable requests per minute
- Per-IP tracking
- Automatic cleanup

## System Management

### Service Control
```bash
sudo systemctl status bar-blinker    # Status check
sudo systemctl restart bar-blinker   # Service restart
journalctl -u bar-blinker -f         # Log monitoring
```

### Health Monitoring
- Status levels:
  - healthy: System operational
  - degraded: Minor issues detected
  - critical: Major functionality impaired
- Metrics tracked:
  - Connection status
  - Failed attempts
  - Button press count
  - Last error message
  - Recovery attempts

### Error Resolution
1. Connection Issues
   - Check WLED IP configuration
   - Verify network connectivity
   - Review authentication settings
   - Check system logs

2. Input Problems
   - Verify GPIO connections
   - Check input device functionality
   - Review bounce settings
   - Monitor hardware logs

3. LED Control Issues
   - Verify WLED configuration
   - Check power supply
   - Review color settings
   - Monitor state transitions

## License
MIT License - See LICENSE file for details.

## External Dependencies
- WLED Firmware
- Flask Framework
- RPi.GPIO Library
