# WLED Button Control

A Python script for controlling WLED devices using a Raspberry Pi push-button. This script enables simple physical control of your WLED installation through button presses, with different behaviors for short and long presses.

## Features

- **Short Press**: Triggers a 30-second green blink pattern
- **Long Press**: Activates red blinking while the button is held down
- **Auto-Recovery**: Automatically reconnects to WLED if connection is lost
- **Robust Error Handling**: Comprehensive logging and error recovery
- **Configurable Settings**: Easy customization through a central configuration class
- **Thread-Safe Operations**: Ensures reliable operation with concurrent state changes

## Hardware Requirements

- Raspberry Pi (any model)
- Push button (momentary switch)
- WLED-compatible LED strip/device
- Basic wiring components (wires, resistors if needed)

## Hardware Setup

1. **Button Connection**:
   - Connect one terminal of your push button to GPIO 18 (BCM numbering)
   - Connect the other terminal to GND (ground)
   - The script uses internal pull-up resistors, so no external resistor is needed

2. **WLED Device**:
   - Ensure your WLED device is properly set up and connected to your network
   - Note down its IP address (you'll need this for configuration)

## Software Prerequisites

1. **Operating System**:
   ```bash
   # Update your Raspberry Pi OS
   sudo apt update
   sudo apt upgrade
   ```

2. **Python Requirements**:
   ```bash
   # Install required Python packages
   sudo apt install python3-pip
   pip3 install RPi.GPIO requests
   ```

## Installation

1. **Clone or Download**:
   ```bash
   # Clone this repository (if using git)
   git clone [repository-url]
   cd wled-button
   ```

2. **Configuration**:
   - Open `wled_button.py` in your preferred editor
   - Modify the `Config` class settings:
     ```python
     class Config:
         BUTTON_PIN = 18  # Change if using different GPIO pin
         WLED_IP = "192.168.6.12"  # Change to your WLED device's IP
         
         # Adjust timing settings if desired
         LONG_PRESS_THRESHOLD = 6.0
         SHORT_FLASH_DURATION = 30.0
         FLASH_INTERVAL = 0.5
         FLASH_BRIGHTNESS = 255
     ```

3. **Make Executable**:
   ```bash
   chmod +x wled_button.py
   ```

## Running the Script

### Manual Execution
```bash
./wled_button.py
```

### Run as a Service

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/wled-button.service
   ```

2. Add the following content:
   ```ini
   [Unit]
   Description=WLED Button Control
   After=network.target

   [Service]
   ExecStart=/usr/bin/python3 /full/path/to/wled_button.py
   WorkingDirectory=/full/path/to/script/directory
   StandardOutput=inherit
   StandardError=inherit
   Restart=always
   User=pi

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl enable wled-button
   sudo systemctl start wled-button
   ```

4. Check service status:
   ```bash
   sudo systemctl status wled-button
   ```

## Configuration Options

The `Config` class provides several customizable parameters:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `BUTTON_PIN` | GPIO pin number (BCM) | 18 |
| `WLED_IP` | IP address of WLED device | "192.168.6.12" |
| `LONG_PRESS_THRESHOLD` | Seconds to trigger long press | 6.0 |
| `SHORT_FLASH_DURATION` | Duration of green flash (seconds) | 30.0 |
| `FLASH_INTERVAL` | Blink interval (seconds) | 0.5 |
| `FLASH_BRIGHTNESS` | LED brightness during flashing | 255 |
| `LOG_FILE` | Path to log file | "~/wled_button.log" |
| `MAX_RETRIES` | Maximum retry attempts | 3 |
| `RETRY_DELAY` | Base delay between retries (seconds) | 1 |
| `RECONNECT_DELAY` | Base delay for reconnection (seconds) | 5 |
| `TRANSITION_TIME` | Color transition time (seconds) | 0.0 |
| `REQUEST_TIMEOUT` | HTTP request timeout (seconds) | 5 |

## Color Configuration

The script uses specific RGB values for different states:

- **White** (Default): `(255, 255, 255)`
- **Green** (Short Press): `(0, 0, 255)` - Note: May need adjustment based on your LED strip's color order
- **Red** (Long Press): `(0, 255, 0)` - Note: May need adjustment based on your LED strip's color order

Adjust these values in the code according to your LED strip's color order (RGB/GRB/etc).

## Logging

The script maintains detailed logs for troubleshooting:

- Log file location: `~/wled_button.log`
- Implements log rotation (1MB file size, keeps 5 backups)
- Logs both to file and console
- Different log levels (INFO, WARNING, ERROR) for easy filtering

View logs using:
```bash
tail -f ~/wled_button.log
```

## Error Handling and Recovery

The script includes robust error handling:

- **Connection Loss**: Automatically attempts to reconnect with exponential backoff
- **Request Failures**: Implements retry logic with configurable attempts
- **State Recovery**: Maintains last known state for recovery after errors
- **Configuration Validation**: Validates all settings at startup

## Troubleshooting

1. **Button Not Responding**:
   - Check GPIO connection
   - Verify `BUTTON_PIN` setting matches your wiring
   - Check button for physical issues
   - Ensure script has GPIO permissions

2. **WLED Connection Issues**:
   - Verify WLED device IP address
   - Check network connectivity
   - Ensure WLED device is powered and operational
   - Check firewall settings

3. **Wrong Colors**:
   - Adjust RGB values in `set_color()` calls
   - Common LED strip color orders: RGB, GRB, BGR
   - Test with different color combinations

4. **Service Won't Start**:
   - Check logs: `journalctl -u wled-button`
   - Verify Python dependencies
   - Check file permissions
   - Validate service file path settings

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- WLED Project: https://github.com/Aircoookie/WLED
- RPi.GPIO documentation: https://pypi.org/project/RPi.GPIO/
