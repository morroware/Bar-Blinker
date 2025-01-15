# Bar-Blinker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

A Python-based controller for WLED LED strips using Raspberry Pi GPIO input and web configuration. The system monitors contact closure events through GPIO to control LED strip states via the WLED API.

## Table of Contents

1. [Features](#features)
2. [Technical Specifications](#technical-specifications)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Hardware Setup](#hardware-setup)
6. [Configuration](#configuration)
7. [Operation](#operation)
8. [System Architecture](#system-architecture)
9. [Service Setup](#service-setup)
10. [Logging](#logging)
11. [Troubleshooting](#troubleshooting)
12. [Security Notes](#security-notes)
13. [License](#license)

## Features

### Input Control
- Short contact: Triggers blue flash sequence (configurable duration)
- Long contact: Triggers red flash sequence while held
- Auto-reversion to default state (white or effect)
- Press override: Long contact during blue sequence switches to red

### Web Interface
- Real-time configuration updates
- Contact closure simulation
- Effect selection and customization
- System health monitoring
- Connection status tracking

### Technical Features
- Multi-threaded operation (GPIO, Web, Connection management)
- Automatic connection recovery
- Configurable retry logic
- State preservation
- Rotating log system

## Technical Specifications

### Input Processing
- Contact closure detection via GPIO
- Configurable pull-up/pull-down resistance
- Software-based debounce implementation
- Contact closure duration tracking

### Threading Architecture
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

### State Control Logic
- Short contact (< configurable threshold):
  - Initiates blue notification sequence
  - Configurable timeout
  - Subsequent triggers ignored during active sequence
  - Automatic state restoration

- Sustained contact (≥ threshold):
  - Triggers red alert sequence
  - Maintains state during contact closure
  - Overrides current sequence
  - Returns to default on release

### State Machine Logic
- Contact States:
  - Idle: No input detected
  - Short: < threshold seconds
  - Long: ≥ threshold seconds
  - Debounce: Input stabilization period

- LED States:
  - Default: White (RGB: 255,255,255)
  - Notification: Blue (RGB: 0,0,255)
  - Alert: Red (RGB: 255,0,0)
  - Off: Transitional (RGB: 0,0,0)

## Requirements

### Hardware
- Raspberry Pi (any model with GPIO)
- Input device options:
  - Momentary push button (common)
  - Mechanical relay contacts
  - Solid state relay outputs
  - Transistor/optocoupler outputs
  - Industrial control contacts
- WLED-compatible controller (ESP8266/ESP32)
- LED strip with appropriate power supply

### Input Device Specifications
- Operating voltage: 3.3V DC
- Maximum current: 8mA per GPIO
- Contact resistance: < 100Ω
- Isolation: Required for industrial inputs
- Debounce: Software implemented

### Software Requirements
- Raspberry Pi OS (Buster or newer)
- Python 3.6+
- Required packages:
  ```
  flask>=2.0.0
  requests>=2.25.1
  RPi.GPIO>=0.7.0
  ```

## Installation

### System Setup
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv python3-dev
```

### Application Setup
```bash
# Clone repository
git clone [repository-url]
cd bar-blinker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp blinker-configs.ini.example blinker-configs.ini
```

## Hardware Setup

### Basic Input Wiring
```
GPIO 18 ─── Input Device ─── GND
         │
         └── Internal Pull-Up Enabled
```

### Protected Input
```
GPIO 18 ─── 1kΩ ─── Contact ─── GND
         │
         └── Internal Pull-Up
```

### Optoisolated Input
```
GPIO 18 ─── 1kΩ ─┐
         │       └── Optocoupler ─── External Input
         └── Pull-Up
```

### Network Setup
- WLED controller requirements:
  - Static IP recommended
  - Network accessibility from Raspberry Pi
  - Same subnet placement
  - Port 5000 accessible for web interface

## Configuration

### Core Settings (blinker-configs.ini)
```ini
[BLINKER]
BUTTON_PIN = 18              # GPIO input pin
WLED_IP = "192.168.1.15"    # WLED controller address
LONG_PRESS_THRESHOLD = 3.0   # Sustained contact threshold
SHORT_FLASH_DURATION = 5.0   # Notification sequence duration
FLASH_INTERVAL = 0.5        # State change interval
FLASH_BRIGHTNESS = 255      # LED intensity (0-255)
```

### Advanced Parameters
- `DEFAULT_EFFECT_SPEED`: Effect speed (0-255)
- `DEFAULT_EFFECT_INTENSITY`: Effect intensity (0-255)
- `MAX_RETRIES`: Connection retry attempts
- `RETRY_DELAY`: Seconds between retries
- `RECONNECT_DELAY`: Base delay for reconnection
- `TRANSITION_TIME`: Color fade duration
- `REQUEST_TIMEOUT`: API request timeout

### Safety Considerations
1. Voltage Protection
   - Never exceed 3.3V on GPIO pins
   - Use voltage dividers for higher voltages
   - Consider optoisolation for industrial inputs

2. Current Protection
   - Include series resistors
   - Monitor total GPIO current
   - Use buffers for high-current situations

3. EMI/RFI Protection
   - Use shielded cables for long runs
   - Add snubber circuits for inductive loads
   - Consider ferrite beads on input wires

## Operation

### Web Interface
Access via: `http://<raspberry-pi-ip>:5000`

Features:
- Live configuration updates
- Input simulation controls
- Effect selection and customization
- System health dashboard
- Connection status monitoring

### API Endpoints
- `/`: Main configuration interface
- `/update_config`: Configuration updates
- `/simulate_press`: Input simulation
- `/health`: System status information

### State Transitions
1. Default State:
   - White mode: Constant white
   - Effect mode: Selected WLED effect

2. Transition States:
   - Blue flash: Short contact indicator
   - Red flash: Long contact indicator
   - Off: Between flash cycles

3. Recovery States:
   - Connection lost: Auto-retry with backoff
   - Error state: Automatic recovery attempt
   - Default reversion: After sequence completion

## Service Setup

### Systemd Service
Create `/etc/systemd/system/bar-blinker.service`:
```ini
[Unit]
Description=Bar Blinker WLED Controller
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/bar-blinker
ExecStart=/home/pi/bar-blinker/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service Management
```bash
sudo systemctl enable bar-blinker
sudo systemctl start bar-blinker
sudo systemctl status bar-blinker
journalctl -u bar-blinker -f
```

## Logging

### Configuration
- Default location: `/home/pi/wled_button.log`
- Rotation: 1MB file size
- Keeps 5 backup files
- Includes timestamps and thread IDs

### Log Levels
- INFO: Normal operation
- WARNING: Recoverable issues
- ERROR: Operation failures
- DEBUG: Detailed diagnostics (disabled by default)

## Troubleshooting

### Common Issues

1. Input Unresponsive
   - Verify GPIO pin number (BCM mode)
   - Check input device connections
   - Confirm ground connection
   - Review permissions

2. WLED Connection Failed
   - Verify IP address
   - Check network connectivity
   - Confirm WLED device power
   - Test with `ping`

3. Web Interface Issues
   - Check Flask server status
   - Verify port 5000 access
   - Check firewall settings
   - Confirm network routing

### Debug Mode
Enable debug logging in `app.py`:
```python
logger.setLevel(logging.DEBUG)
```

## Security Notes

1. Network Security
   - Web interface has no authentication
   - Restrict to local network
   - Consider reverse proxy for remote access

2. File Permissions
   - Log file needs write access
   - Config file needs read access
   - GPIO requires root or gpio group

3. Rate Limiting
   - API requests limited to 100/minute
   - Connection retries use exponential backoff
   - Automatic timeout on failed connections

## License

MIT License - See LICENSE file for details
