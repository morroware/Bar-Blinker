# WLED Button Controller for Raspberry Pi

A Python script that integrates a Raspberry Pi with a WLED-based LED strip through a single physical button. When pressed, the button triggers a flashing green sequence on the WLED strip before returning it to white. The script is designed to run as a service with automatic reconnection and error recovery features.

## Table of Contents

1. [Features](#features)
2. [Hardware Requirements](#hardware-requirements)
3. [Software Requirements](#software-requirements)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Usage](#usage)
7. [How It Works](#how-it-works)
8. [Troubleshooting](#troubleshooting)
9. [License](#license)

## Features

- **Simple Button Control**: Single button press triggers LED sequence
- **Visual Feedback**: LEDs flash green during activation
- **Auto-Reconnection**: 
  - Handles network disconnections
  - Automatically reconnects to WLED device
  - Restores previous state after connection issues
- **Persistent Operation**: 
  - Runs as a system service
  - Survives network interruptions
  - Automatically starts on boot
- **Detailed Logging**: 
  - Maintains rotating log files for troubleshooting
  - Prevents excessive file growth
  - Stores logs in `/var/log/wled_button.log`
- **State Preservation**:
  - Saves initial white state as WLED preset 1
  - Can restore last known state if interrupted
- **Error Handling**: Gracefully handles various failure scenarios

## Hardware Requirements

### Components Needed
- Raspberry Pi (any modern model)
- WLED-compatible LED controller (ESP8266/ESP32 running WLED)
- LED strip compatible with WLED (e.g., WS2812B)
- Momentary push button
- Basic wiring materials

### Wiring Instructions

1. **Button Connection**:
   - Connect one pin of the button to GPIO 18 (BCM numbering)
   - Connect the other pin to any GND (Ground) pin
   - No external resistor needed (internal pull-up is used)

2. **WLED Device**:
   - No physical connection needed between Pi and WLED device
   - Communication happens over network (Ethernet/Wi-Fi)
   - Follow standard WLED wiring for LED strip connection:
     - Data pin on WLED controller to LED strip data-in
     - Proper power and ground connections

## Software Requirements

1. **Operating System**:
   - Raspberry Pi OS (Buster, Bullseye, or later)
   - Other Linux distributions should work but are untested

2. **Python Dependencies**:
   ```bash
   sudo apt-get update
   sudo apt-get install python3-rpi.gpio
   pip3 install requests
   ```

## Installation

1. **Get the Code**:
   ```bash
   git clone https://github.com/yourusername/wled-button-controller.git
   cd wled-button-controller
   ```
   Or download just the Python script if preferred.

2. **Make Executable** (Optional):
   ```bash
   chmod +x wled_button_controller.py
   ```

3. **Set Up System Service**:
   Create service file:
   ```bash
   sudo nano /etc/systemd/system/wled-button.service
   ```
   
   Add the following content:
   ```ini
   [Unit]
   Description=WLED Button Control Service
   After=network.target

   [Service]
   ExecStart=/usr/bin/python3 /path/to/your/wled_button.py
   Restart=always
   User=pi
   Group=pi

   [Install]
   WantedBy=multi-user.target
   ```

4. **Enable and Start Service**:
   ```bash
   sudo systemctl enable wled-button
   sudo systemctl start wled-button
   ```

## Configuration

Edit these variables in the script to customize behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `BUTTON_PIN` | 18 | GPIO pin for button (BCM numbering) |
| `WLED_IP` | "192.168.1.100" | IP address of WLED device |
| `FLASH_DURATION` | 30 | Duration of flash sequence (seconds) |
| `FLASH_INTERVAL` | 0.5 | Time for one flash cycle (seconds) |
| `FLASH_BRIGHTNESS` | 255 | Brightness of green flash (0-255) |
| `TRANSITION_TIME` | 0.0 | Color transition time (seconds) |
| `MAX_RETRIES` | 3 | Number of retry attempts |
| `RETRY_DELAY` | 1 | Seconds between retries |
| `RECONNECT_DELAY` | 5 | Seconds between reconnection attempts |

## Usage

1. **Running the Script**:
   ```bash
   python3 wled_button_controller.py
   ```
   Or if running as service:
   ```bash
   sudo systemctl start wled-button
   ```

2. **Operation**:
   - Press button to trigger sequence
   - LEDs flash green for configured duration
   - Return to solid white after sequence
   - Any interruption triggers state restoration

3. **Monitoring**:
   ```bash
   sudo systemctl status wled-button    # Check service status
   sudo tail -f /var/log/wled_button.log # View logs
   ```

## How It Works

1. **Initialization**:
   - Sets up rotating log file
   - Configures GPIO with internal pull-up
   - Establishes WLED connection

2. **WLED Communication**:
   - Uses WLED HTTP API
   - Fetches device info from `/json/info`
   - Sends states via `/json/state`
   - Includes retry mechanism for reliability

3. **Button Handling**:
   - Detects falling edge (button press)
   - Includes debounce protection
   - Triggers flash sequence
   - Handles cleanup on exit

4. **Flash Sequence**:
   - Alternates between green and off
   - Uses precise timing for intervals
   - Manages state transitions
   - Includes error recovery

## Troubleshooting

1. **Service Issues**:
   - Check logs: `sudo journalctl -u wled-button`
   - Verify Python dependencies
   - Confirm script path in service file
   - Check file permissions

2. **Button Problems**:
   - Verify GPIO connections
   - Check pin number configuration
   - Test button continuity
   - Confirm ground connection

3. **WLED Connection Failures**:
   - Verify IP address
   - Check network connectivity
   - Ensure same network/subnet
   - Check WLED device status
   - Verify no firewall blocking
   - Check for custom ports

4. **LED Strip Issues**:
   - Verify WLED configuration
   - Check physical connections
   - Confirm LED count settings
   - Test power supply

5. **Log File Problems**:
   - Check `/var/log` permissions
   - Verify disk space
   - Test log rotation
   - Ensure proper ownership

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [WLED Project](https://github.com/Aircoookie/WLED)
- Raspberry Pi GPIO Documentation
