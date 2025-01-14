# WLED Button Controller

## Overview
The **WLED Button Controller** is a Python-based application running on a Raspberry Pi that manages WLED-powered LED strips through a single physical button. It distinguishes between different types of button presses to execute corresponding LED behaviors:

* **Short Press:**
   * **Action:** A quick press of the button.
   * **Behavior:** The LED strips blink green for a configurable duration (e.g., 30 seconds), providing a brief visual notification or alert.

* **Long Press:**
   * **Action:** Holding down the button for longer than a specified threshold (e.g., 6 seconds).
   * **Behavior:** The LED strips initiate a continuous red blinking sequence while the button remains pressed, indicating a sustained alert or action.

* **Press Release After Long Press:**
   * **Action:** Releasing the button after a long press.
   * **Behavior:** The LED strips revert to a steady white color, signaling the end of the long-press action.

These distinct button interactions allow users to intuitively control LED colors and patterns, enabling both quick notifications and sustained alerts based on their input.

## Features
* Single-button interface for multiple LED patterns
* Web-based configuration interface
* Configurable timing parameters
* Automatic reconnection handling
* Comprehensive logging system
* Thread-safe operations
* Configuration persistence using INI files

## Hardware Requirements
* Raspberry Pi (any model with GPIO pins)
* Momentary push button
* 10kΩ resistor (optional - internal pull-up resistor can be used)
* WLED-compatible LED controller (e.g., ESP8266/ESP32 running WLED)
* LED strip compatible with your WLED controller

## Software Requirements
* Raspberry Pi OS (formerly Raspbian)
* Python 3.6 or higher
* pip (Python package manager)
* Required Python packages:
  * Flask
  * requests
  * RPi.GPIO

## Hardware Setup

### Button Wiring
1. Connect one terminal of the button to GPIO 18 (default, configurable)
2. Connect the other terminal to GND (Ground)
   - Note: The code uses the internal pull-up resistor, but you can add an external 10kΩ pull-up resistor for additional reliability

### Basic Circuit Diagram
```
Raspberry Pi     Button
GPIO 18  -------|/------
                        |
GND      --------------)
```

## Software Installation

1. Update your Raspberry Pi:
```bash
sudo apt update
sudo apt upgrade
```

2. Install required Python packages:
```bash
sudo apt install python3-pip
pip3 install flask requests RPi.GPIO
```

3. Create project directory and structure:
```bash
mkdir ~/wled-button
cd ~/wled-button
mkdir templates
```

4. Create the following files:
- `bar-blinker.py` (main script)
- `blinker-configs.ini` (configuration file)
- `templates/index.html` (web interface template)

5. Make the main script executable:
```bash
chmod +x bar-blinker.py
```

## Configuration

### Initial Setup
Create `blinker-configs.ini` with the following content:
```ini
[BLINKER]
BUTTON_PIN = 18
WLED_IP = "192.168.6.12"
LONG_PRESS_THRESHOLD = 6.0
SHORT_FLASH_DURATION = 30.0
FLASH_INTERVAL = 0.5
FLASH_BRIGHTNESS = 255
LOG_FILE = ~/wled_button.log
MAX_RETRIES = 3
RETRY_DELAY = 1
RECONNECT_DELAY = 5
TRANSITION_TIME = 0.0
REQUEST_TIMEOUT = 5
```

### Key Configuration Parameters
* **BUTTON_PIN**: GPIO pin number where button is connected (default: 18)
* **WLED_IP**: IP address of your WLED device
* **LONG_PRESS_THRESHOLD**: Time in seconds to trigger long press (default: 6.0)
* **SHORT_FLASH_DURATION**: Duration of green blinking sequence in seconds (default: 30.0)
* **FLASH_INTERVAL**: Time between blinks in seconds (default: 0.5)
* **FLASH_BRIGHTNESS**: LED brightness level (0-255, default: 255)

## Running as a Service

1. Create systemd service file:
```bash
sudo nano /etc/systemd/system/wled-button.service
```

2. Add the following content:
```ini
[Unit]
Description=WLED Button Controller
After=network.target

[Service]
ExecStart=/home/pi/wled-button/bar-blinker.py
WorkingDirectory=/home/pi/wled-button
User=pi
Group=pi
Restart=always

[Install]
WantedBy=multi-user.target
```

3. Enable and start the service:
```bash
sudo systemctl enable wled-button
sudo systemctl start wled-button
```

## Web Interface
* Access at: `http://<raspberry-pi-ip>:5000`
* Features:
  * Configuration parameter adjustment
  * Button press simulation
  * System status monitoring
  * Visual feedback for actions

## Behavior Details

### Short Press Sequence
1. Button is pressed and released before LONG_PRESS_THRESHOLD
2. LED strip begins green blinking sequence
3. Alternates between:
   - Green (RGB: 0, 255, 0) at configured brightness
   - Off state
4. Continues for SHORT_FLASH_DURATION seconds
5. Returns to solid white
6. Additional short presses during green sequence are ignored

### Long Press Sequence
1. Button is held for longer than LONG_PRESS_THRESHOLD
2. LED strip begins red blinking sequence
3. Alternates between:
   - Red (RGB: 255, 0, 0) at configured brightness
   - Off state
4. Continues while button is held
5. Returns to solid white on release

### Error Handling
* Automatic reconnection to WLED device if connection is lost
* Exponential backoff for retry attempts
* Comprehensive logging of errors and events
* Graceful degradation if components fail

## Troubleshooting

### Common Issues
1. **LED Strip Not Responding**
   - Verify WLED_IP is correct
   - Check WLED device is powered and connected
   - Review logs for connection errors

2. **Button Not Working**
   - Verify GPIO pin configuration
   - Check button wiring
   - Test button with multimeter

3. **Web Interface Inaccessible**
   - Check network connectivity
   - Verify service is running
   - Check for port conflicts

### Logging
* Default log location: `~/wled_button.log`
* Log rotation: 1MB file size, 5 backup files
* Contains:
  - Connection status
  - Button events
  - Error messages
  - Configuration changes


## Maintenance

### Service Management
```bash
# Check status
sudo systemctl status wled-button

# Stop service
sudo systemctl stop wled-button

# Start service
sudo systemctl start wled-button

# Restart service
sudo systemctl restart wled-button

# View logs
journalctl -u wled-button
```

### Updates
1. Stop the service
2. Update code files
3. Test configuration
4. Restart service

## Support and Development

### Monitoring
* Check service status regularly
* Monitor log files for errors
* Verify network connectivity
* Test button functionality

