# Bar-Blinker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

A Python-based controller for WLED LED strips using Raspberry Pi GPIO input and web configuration. The system monitors button press events to control LED states and provides a comprehensive web interface for configuration.

## Features

### Button Control
- Short press: Triggers blue flash sequence (configurable duration)
- Long press: Triggers red flash sequence while held
- Auto-reversion to default state (white or effect)
- Press override: Long press during blue sequence switches to red

### Web Interface
- Real-time configuration updates
- Button press simulation
- Effect selection and customization
- System health monitoring
- Connection status tracking

### Technical Features
- Multi-threaded operation (GPIO, Web, Connection management)
- Automatic connection recovery
- Configurable retry logic
- State preservation
- Rotating log system

## Requirements

### Hardware
- Raspberry Pi (any model with GPIO)
- Momentary push button
- WLED-compatible LED controller
- Network connectivity between Pi and WLED

### Software
- Python 3.7+
- Required packages:
  ```
  flask>=2.0.0
  requests>=2.25.1
  RPi.GPIO>=0.7.0
  ```

## Hardware Setup

### Button Wiring
```
GPIO 18 ─── Button ─── GND
```
- Uses internal pull-up resistor (no external components needed)
- Active-low logic
- Can change pin in configuration (requires restart)

### Network Requirements
- WLED device must have static IP
- Same subnet as Raspberry Pi
- Port 5000 accessible for web interface

## Installation

### 1. System Preparation
```bash
sudo apt update && sudo apt upgrade
sudo apt install -y python3-pip python3-venv python3-dev
```

### 2. Application Setup
```bash
# Clone repository
git clone [repository-url]
cd bar-blinker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
```bash
# Copy example config
cp blinker-configs.ini.example blinker-configs.ini

# Edit configuration
nano blinker-configs.ini
```

## Configuration Parameters

### Core Settings (blinker-configs.ini)
```ini
[BLINKER]
BUTTON_PIN = 18
WLED_IP = "192.168.1.15"
LONG_PRESS_THRESHOLD = 3.0
SHORT_FLASH_DURATION = 5.0
FLASH_INTERVAL = 0.5
FLASH_BRIGHTNESS = 255
```

### Advanced Parameters
- `DEFAULT_EFFECT_SPEED`: Effect animation speed (0-255)
- `DEFAULT_EFFECT_INTENSITY`: Effect parameter intensity (0-255)
- `MAX_RETRIES`: Connection retry attempts
- `RETRY_DELAY`: Seconds between retries
- `RECONNECT_DELAY`: Base delay for reconnection attempts
- `TRANSITION_TIME`: Color fade duration
- `REQUEST_TIMEOUT`: API request timeout

## Operation

### Button Functions

1. Short Press (< threshold seconds)
   - Triggers blue flash sequence
   - Duration set by SHORT_FLASH_DURATION
   - Returns to default state after sequence
   - Can be interrupted by long press

2. Long Press (≥ threshold seconds)
   - Initiates red flash sequence
   - Maintains sequence while held
   - Returns to default on release
   - Overrides any active short press sequence

### Web Interface
Access via: `http://<raspberry-pi-ip>:5000`

Features:
- Live configuration updates
- Button simulation controls
- Effect selection and customization
- System health dashboard
- Connection status monitoring

### States and Transitions
1. Default State:
   - White mode: Constant white illumination
   - Effect mode: Running selected WLED effect

2. Transition States:
   - Blue flash: Short press indicator
   - Red flash: Long press indicator
   - Off: Between flash cycles

3. Recovery States:
   - Connection lost: Auto-retry with backoff
   - Error state: Automatic recovery attempt
   - Default reversion: After sequence completion

## System Architecture

### Threading Model
1. Main Thread:
   - Flask web server
   - Configuration management
   - Request handling

2. GPIO Thread:
   - Button state monitoring
   - Debounce handling
   - Press duration tracking

3. Connection Thread:
   - WLED connectivity monitoring
   - Auto-reconnection
   - State recovery

### Communication Flow
```
Button Press → GPIO Thread → State Manager → WLED API
     ↑                           ↑
Web Interface                Connection Monitor
```

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
# Enable service
sudo systemctl enable bar-blinker

# Start service
sudo systemctl start bar-blinker

# Check status
sudo systemctl status bar-blinker

# View logs
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

1. Button Unresponsive
   - Verify GPIO pin number (BCM mode)
   - Check button connections
   - Confirm ground connection
   - Check permissions

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

### Health Checks
The system performs automatic health monitoring:
- Connection status
- Response times
- Error rates
- Button press tracking

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
