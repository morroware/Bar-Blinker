# Bar-Blinker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)


A Raspberry Pi-based controller for WLED LED strips featuring a physical button interface and web configuration panel. Bar-Blinker provides an intuitive way to control LED notifications through a simple button interface while offering advanced configuration through a web panel.

## 📋 Table of Contents

- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Hardware Setup](#-hardware-setup)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Technical Details](#-technical-details)
- [Troubleshooting](#-troubleshooting)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)

## ✨ Features

### Single-Button Control Interface
The core of Bar-Blinker is its intuitive single-button control system:

* **Short Press Functionality**
    * Triggers a configurable green notification sequence
    * Perfect for service calls or attention signals
    * Automatically times out after 30 seconds (configurable)
    * Smart debouncing prevents accidental triggers
    * Ignores additional short presses during active sequence

* **Long Press Functionality**
    * Activates immediate red alert sequence
    * Maintains alert state while button is held
    * Ideal for emergency or priority signaling
    * Can interrupt any ongoing sequence
    * Returns to default state upon release

* **Default State**
    * Maintains steady white illumination
    * Provides ambient lighting when not signaling
    * Automatic state restoration after sequences

### Web Configuration Interface
A responsive, browser-based control panel offering:

* **Real-Time Controls**
    * Live parameter adjustment
    * Button press simulation
    * Immediate feedback
    * Mobile-friendly design

* **System Monitoring**
    * Connection status display
    * LED state visualization
    * Log file access
    * Configuration overview

### Robust Operation
Built for reliability in demanding environments:

* **Thread Safety**
    * Concurrent operation handling
    * State synchronization
    * Resource locking mechanisms
    * Clean shutdown procedures

* **Connection Management**
    * Automatic WLED reconnection
    * Exponential backoff
    * Connection state monitoring
    * Error recovery

* **Configuration System**
    * INI file-based configuration
    * Runtime parameter updates
    * Validation checking
    * Default fallbacks

## 🔧 Requirements

### Hardware Requirements

* **Raspberry Pi**
    * Any model with GPIO pins
    * Stable 5V power supply
    * Network connectivity
    * Minimum 512MB RAM

* **Input Hardware**
    * Momentary push button (normally open)
    * Optional: 10kΩ pull-up resistor
    * Connecting wires

* **LED System**
    * WLED-compatible controller (ESP8266/ESP32)
    * Compatible LED strip
    * Adequate power supply for LEDs

### Software Requirements

* **System**
    * Raspberry Pi OS (Buster or newer)
    * Python 3.6 or higher
    * Network configuration
    * SSH access (recommended)

* **Python Packages**
    ```bash
    flask>=2.0.0
    requests>=2.25.1
    RPi.GPIO>=0.7.0
    ```

## 🚀 Installation

### 1. System Preparation
```bash
# Update system packages
sudo apt update
sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3-pip git
```

### 2. Repository Setup
```bash
# Clone the repository
git clone https://github.com/morroware/Bar-Blinker.git
cd Bar-Blinker

# Install Python dependencies
pip3 install -r requirements.txt
```

### 3. Configuration
```bash
# Copy example configuration
cp config/blinker-configs.ini.example blinker-configs.ini

# Edit configuration
nano blinker-configs.ini
```

### 4. Service Installation
```bash
# Copy service file
sudo cp systemd/bar-blinker.service /etc/systemd/system/

# Enable and start service
sudo systemctl enable bar-blinker
sudo systemctl start bar-blinker
```

## 🔌 Hardware Setup

### Button Installation

1. **Wiring Diagram**
    ```
    Raspberry Pi    Button     Ground
    GPIO 18   ──────[BTN]──────GND
    ```

2. **Pin Configuration**
    * GPIO 18 (default, configurable)
    * Internal pull-up enabled
    * Active-low configuration
    * Debounce handling in software

### LED Controller Setup

1. **WLED Installation**
    * Flash WLED to your controller
    * Configure WiFi settings
    * Note the IP address

2. **Network Configuration**
    * Static IP recommended
    * Same subnet as Raspberry Pi
    * Accessible by Raspberry Pi

## ⚙️ Configuration

### Primary Configuration File (blinker-configs.ini)

```ini
[BLINKER]
# Hardware Configuration
BUTTON_PIN = 18              # GPIO pin for button input
WLED_IP = "192.168.6.12"     # WLED controller IP address

# Timing Parameters
LONG_PRESS_THRESHOLD = 6.0    # Seconds to trigger long press
SHORT_FLASH_DURATION = 30.0   # Green sequence duration
FLASH_INTERVAL = 0.5         # Seconds between state changes

# LED Parameters
FLASH_BRIGHTNESS = 255       # LED brightness (0-255)
TRANSITION_TIME = 0.0        # Color transition time

# System Parameters
LOG_FILE = "~/wled_button.log"
MAX_RETRIES = 3
RETRY_DELAY = 1
```

### Web Interface Access
* URL: `http://<raspberry-pi-ip>:5000`
* Default port: 5000
* All settings adjustable through interface

## 🎮 Usage

### Physical Button Operation

1. **Short Press** (< 6 seconds)
    * Quick press and release
    * Triggers green notification sequence
    * Times out automatically
    * Ideal for service requests

2. **Long Press** (≥ 6 seconds)
    * Press and hold
    * Activates red alert sequence
    * Maintains until release
    * Priority signaling

3. **Release Actions**
    * Short press: Completes green sequence
    * Long press: Returns to white
    * Any sequence: Clean state restoration

### Web Interface Controls

1. **Configuration Panel**
    * All timing parameters
    * LED brightness control
    * Network settings
    * System status

2. **Simulation Controls**
    * Short press testing
    * Long press simulation
    * Immediate feedback

## 🔍 Technical Details

### Threading Architecture

1. **Main Thread**
    * Web server (Flask)
    * Configuration management
    * Service lifecycle

2. **Hardware Thread**
    * Button state monitoring
    * Debounce handling
    * Event triggering

3. **Connection Thread**
    * WLED communication
    * Reconnection handling
    * State management

### State Management

1. **LED States**
    * White: Default/Ready
    * Green Blinking: Notification
    * Red Blinking: Alert
    * Off: Transitioning

2. **Button States**
    * Idle: No press
    * Short Press: Processing
    * Long Press: Active
    * Debounce: Waiting

### Logging System

* **Location**: `~/wled_button.log`
* **Rotation**: 1MB size, 5 backups
* **Level**: INFO default
* **Format**: Timestamp, level, message

## 🔧 Troubleshooting

### Common Issues

1. **Button Unresponsive**
    * Check GPIO connections
    * Verify configuration
    * Review system logs

2. **LED Control Fails**
    * Verify WLED IP address
    * Check network connectivity
    * Confirm power to LED controller

3. **Web Interface Inaccessible**
    * Check service status
    * Verify network settings
    * Review Flask logs

### Service Management
```bash
# Status check
sudo systemctl status bar-blinker

# Service restart
sudo systemctl restart bar-blinker

# Log viewing
journalctl -u bar-blinker -f
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgments

* [WLED Project](https://github.com/Aircoookie/WLED) for the excellent LED firmware
* [Flask](https://flask.palletsprojects.com/) for the web framework
* [Raspberry Pi Foundation](https://www.raspberrypi.org/) for GPIO library
