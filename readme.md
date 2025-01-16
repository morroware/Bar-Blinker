# Bar-Blinker: A Raspberry Pi WLED Controller with Button Input and Web Interface

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

A Python-based controller for WLED LED strips using Raspberry Pi GPIO input and a web-based configuration interface. The system monitors contact closure events through a GPIO pin to control LED strip states via the WLED API.

## Table of Contents

1.  [Features](#features)
2.  [Technical Specifications](#technical-specifications)
3.  [Requirements](#requirements)
4.  [Installation](#installation)
5.  [Hardware Setup](#hardware-setup)
6.  [Configuration](#configuration)
7.  [Operation](#operation)
8.  [System Architecture](#system-architecture)
9.  [Service Setup](#service-setup)
10. [Logging](#logging)
11. [Troubleshooting](#troubleshooting)
12. [Security Notes](#security-notes)
13. [License](#license)

## Features

### Input Control

*   Short contact: Triggers blue flash sequence (configurable duration)
*   Long contact: Triggers red flash sequence while held
*   Auto-reversion to default state (white or effect)
*   Long press override: Long contact during blue sequence switches to red

### Web Interface

*   Real-time configuration updates
*   Contact closure simulation
*   Effect selection and customization
*   System health monitoring
*   Connection status tracking

### Technical Features

*   Multi-threaded operation (GPIO, Web, Connection management)
*   Automatic connection recovery
*   Configurable retry logic
*   State preservation (last known WLED state, configuration settings)
*   Rotating log system

## Technical Specifications

### Input Processing

*   Contact closure detection via GPIO
*   Configurable pull-up/pull-down resistance
*   Software-based debounce implementation
*   Contact closure duration tracking

### Threading Architecture

1.  Main Thread (Flask Web Server)
    *   Handles web interface requests
    *   Configuration management
    *   HTTP endpoints for simulation
    *   Template rendering

2.  Hardware Monitoring Thread
    *   Continuous GPIO state monitoring
    *   Debounce implementation
    *   Contact closure duration tracking
    *   State transition management

3.  Connection Management Thread
    *   Background WLED connectivity
    *   Automatic reconnection logic
    *   Exponential backoff implementation
    *   Connection state monitoring

### State Control Logic

*   Short contact (< configurable threshold):
    *   Initiates blue notification sequence
    *   Configurable timeout
    *   Subsequent triggers ignored during active sequence
    *   Automatic state restoration

*   Sustained contact (≥ threshold):
    *   Triggers red alert sequence
    *   Maintains state during contact closure
    *   Overrides current sequence
    *   Returns to default on release

### State Machine Logic

*   **Contact States:**
    *   **Idle:** No input detected.
    *   **Short Press:** Contact detected for less than the threshold.
    *   **Long Press:** Contact detected for the threshold or longer.
*   **Debouncing:** Software-based debouncing is implemented to filter out spurious contact transitions.
*   **LED States:**
    *   **Default:** White (RGB: 255,255,255) or user-selected WLED effect.
    *   **Notification:** Blue (RGB: 0,0,255).
    *   **Alert:** Red (RGB: 255,0,0).
    *   **Off:** LEDs briefly turned off between color changes during blinking.

## Requirements

### Hardware

*   Raspberry Pi (any model with GPIO)
*   Input device options:
    *   Momentary push button (common)
    *   Mechanical relay contacts
    *   Solid state relay outputs
    *   Transistor/optocoupler outputs
    *   Industrial control contacts
*   WLED-compatible controller (ESP8266/ESP32) - *Note: Ensure you have flashed the WLED firmware onto your ESP device.*
*   LED strip with appropriate power supply

### Input Device Specifications

*   Operating voltage: 3.3V DC
*   Maximum current: 8mA per GPIO (recommended to stay under for total current across all GPIOs)
*   Contact resistance: < 100Ω
*   Isolation: Required for industrial inputs
*   Debounce: Software implemented

### Software Requirements

*   Raspberry Pi OS (Buster or newer)
*   Python 3.6+
*   Required packages:

```
flask>=2.2.0,<2.3.0
requests>=2.25.1,<2.26.0
RPi.GPIO>=0.7.0,<0.8.0
```

## Installation

### System Setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv
```

### Application Setup

```bash
# Clone repository (replace with your repository URL)
git clone https://github.com/your-username/your-repo.git
cd bar-blinker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp blinker-configs.ini.example blinker-configs.ini
nano blinker-configs.ini # Edit this file to set your WLED IP, etc.

# Run the application (for testing)
python app.py
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

Note: The optocoupler provides electrical isolation between the Raspberry Pi and the external input, which is important for safety and noise reduction, especially in industrial environments.

## Configuration

### Core Settings (blinker-configs.ini)

```ini
[BLINKER]
BUTTON_PIN = 18              # GPIO input pin
WLED_IP = "YOUR_WLED_IP"     # Replace with your WLED controller's IP address
LONG_PRESS_THRESHOLD = 3.0   # Sustained contact threshold (seconds)
SHORT_FLASH_DURATION = 5.0   # Notification sequence duration (seconds)
FLASH_INTERVAL = 0.5         # State change interval (seconds)
FLASH_BRIGHTNESS = 255       # LED intensity (0-255)
LOG_FILE = "/home/pi/bar-blinker/wled_button.log" # Path to log file
```

### Advanced Parameters

*   DEFAULT_EFFECT_SPEED: Effect speed (0-255)
*   DEFAULT_EFFECT_INTENSITY: Effect intensity (0-255)
*   MAX_RETRIES: Connection retry attempts
*   RETRY_DELAY: Seconds between retries
*   RECONNECT_DELAY: Base delay for reconnection
*   TRANSITION_TIME: Color fade duration
*   REQUEST_TIMEOUT: API request timeout

### Safety Considerations

#### Voltage Protection

*   Never exceed 3.3V on GPIO pins without appropriate level shifting.
*   Use voltage dividers for higher voltages.
*   Consider optoisolation for industrial inputs.

#### Current Protection

*   Include series resistors.
*   Monitor total GPIO current (recommended maximum is around 50mA total for all pins).
*   Use buffers for high-current situations.

#### EMI/RFI Protection

*   Use shielded cables for long runs.
*   Add snubber circuits for inductive loads.
*   Consider ferrite beads on input wires.

#### Electrostatic Discharge (ESD)

*   Take precautions to avoid static discharge when handling the Raspberry Pi or connected components.

## Operation

### Web Interface

Access via: http://<raspberry-pi-ip>:5000

Features:

*   Live configuration updates
*   Input simulation controls
*   Effect selection and customization
*   System health dashboard
*   Connection status monitoring

### API Endpoints

*   /: Main configuration interface (GET)
*   /update_config: Configuration updates (POST)
*   /simulate_press: Input simulation (POST)
*   /health: System status information (GET)

### State Transitions

#### Default State:

*   White mode: Constant white
*   Effect mode: Selected WLED effect

#### Transition States:

*   Blue flash: Short contact indicator
*   Red flash: Long contact indicator
*   Off: Between flash cycles

#### Recovery States:

*   Connection lost: Auto-retry with backoff
*   Error state: Automatic recovery attempt
*   Default reversion: After sequence completion

## System Architecture

The system consists of three main threads:

1.  Main Thread: Handles the Flask web server, including web interface requests, configuration management, HTTP endpoints for simulation, and template rendering.
2.  Hardware Monitoring Thread: Responsible for continuous GPIO state monitoring, software-based debouncing, contact closure duration tracking, and managing state transitions based on input events.
3.  Connection Management Thread: Manages background WLED connectivity, automatic reconnection logic with exponential backoff, and connection state monitoring.

## Service Setup

### Systemd Service

Create /etc/systemd/system/bar-blinker.service:

```ini
[Unit]
Description=Bar Blinker WLED Controller
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/bar-blinker/bar-blinker
ExecStart=/home/pi/bar-blinker/bar-blinker/venv/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Service Management

```bash
sudo systemctl daemon-reload
sudo systemctl enable bar-blinker
sudo systemctl start bar-blinker
sudo systemctl status bar-blinker
sudo journalctl -u bar-blinker -f
```

## Logging

### Configuration

*   Default location: /home/pi/bar-blinker/wled_button.log (configurable via LOG_FILE in blinker-configs.ini)
*   Rotation: 1MB file size
*   Keeps 5 backup files
*   Includes timestamps and thread IDs

### Log Levels

*   INFO: Normal operation messages (e.g., startup, configuration changes, successful connections).
*   WARNING: Recoverable issues or potential problems (e.g., temporary connection failures, invalid configuration values).
*   ERROR: Operation failures that may require attention (e.g., persistent connection failures, hardware errors).
*   DEBUG: Detailed diagnostic information (e.g., variable values, function calls). Disabled by default.

## Troubleshooting

### Common Issues

#### Input Unresponsive

*   Verify GPIO pin number (BCM mode) in blinker-configs.ini.
*   Check input device connections and ensure they are secure.
*   Confirm ground connection between the input device and the Raspberry Pi.
*   Review permissions for accessing GPIO (user should be in the gpio group).

#### WLED Connection Failed

*   Verify the WLED IP address in blinker-configs.ini.
*   Check network connectivity between the Raspberry Pi and the WLED device.
*   Confirm that the WLED device is powered on and functioning.
*   Test network connectivity using ping <WLED_IP_ADDRESS>.

#### Web Interface Issues

*   Check the Flask server status using sudo systemctl status bar-blinker.
*   Verify that port 5000 is accessible on the Raspberry Pi.
*   Check firewall settings on the Raspberry Pi and any network devices.
*   Confirm network routing allows access to the Raspberry Pi's web server.

### Debug Mode

Enable debug logging in app.py:

```python
logger.setLevel(logging.DEBUG)
```

Note: Debug logging can impact performance. Remember to disable it in production.

View logs with:

```bash
sudo journalctl -u bar-blinker -f  # If using systemd
# OR
tail -f /home/pi/bar-blinker/wled_button.log # If LOG_FILE is customized
```

## Security Notes

### Network Security

*   The web interface has no authentication.
*   Restrict access to the local network.
*   Consider using a reverse proxy with HTTPS and authentication for remote access.

### File Permissions

*   The log file needs write access by the user running the application.
*   The configuration file needs read access by the user running the application.
*   GPIO access may require root privileges or membership in the gpio group.

### Rate Limiting

*   API requests are limited to 100 per minute per IP address to mitigate potential abuse.
*   Connection retries use exponential backoff to avoid overwhelming the WLED device.
*   Automatic timeout on failed connection attempts prevents indefinite hanging.

### Updates

*   Keep the Raspberry Pi OS and all installed packages updated with sudo apt update && sudo apt upgrade.

## License

MIT License - See LICENSE file for details.
