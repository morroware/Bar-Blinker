# WLED Button Controller - Technical Documentation

## Table of Contents
1. [Introduction](#introduction)
2. [Configuration Parameters](#configuration-parameters)
3. [Class Reference: WLEDController](#class-reference-wledcontroller)
4. [Utility Functions](#utility-functions)
5. [Main Program Flow](#main-program-flow)
6. [API Endpoints](#api-endpoints)
7. [Error Handling](#error-handling)
8. [Logging System](#logging-system)

## Introduction

This script provides an interface between a Raspberry Pi and a WLED device over network connections. It monitors a physical button connected to a GPIO pin and triggers LED sequences on button press events. The implementation includes automatic reconnection, state preservation, and comprehensive error handling.

### Key Features:
- Network-based communication with WLED
- Button debouncing and event handling
- Automatic connection recovery
- State preservation and restoration
- Rotating log system
- Clean GPIO resource management

## Configuration Parameters

```python
# GPIO Configuration
BUTTON_PIN = 18        # BCM pin numbering

# Network Settings
WLED_IP = "192.168.1.100"  # WLED device IP address

# Timing Parameters
FLASH_DURATION = 30    # Total flash sequence duration (seconds)
FLASH_INTERVAL = 0.5   # Single flash cycle duration (seconds)
TRANSITION_TIME = 0.0  # Color transition timing (seconds)

# LED Settings
FLASH_BRIGHTNESS = 255 # Maximum brightness (0-255)

# System Configuration
LOG_FILE = "/var/log/wled_button.log"
MAX_RETRIES = 3        # Connection retry attempts
RETRY_DELAY = 1        # Delay between retries (seconds)
RECONNECT_DELAY = 5    # Delay between reconnection attempts (seconds)
```

## Class Reference: WLEDController

### Class Overview
The `WLEDController` class manages all interactions with the WLED device, including connection management, state control, and sequence execution.

### Constructor

```python
def __init__(self, ip_address):
    """
    Initialize WLED controller instance.

    Args:
        ip_address (str): IP address of WLED device
    """
```

### Public Methods

#### Connection Management

```python
def wait_for_connection(self):
    """
    Continuously attempt connection until successful.

    Returns:
        bool: True once connected (never returns False)
    """

def initialize(self):
    """
    Initialize connection and fetch device information.

    Returns:
        bool: True if connection successful, False otherwise
    """

def get_info(self):
    """
    Retrieve WLED device information.

    Returns:
        dict or None: Device information if successful
    """
```

#### State Control

```python
def set_color(self, red, green, blue, brightness=255):
    """
    Set LED strip color and brightness.

    Args:
        red (int): Red value (0-255)
        green (int): Green value (0-255)
        blue (int): Blue value (0-255)
        brightness (int): Overall brightness (0-255)

    Returns:
        bool: Success status
    """

def save_state(self):
    """
    Save current state as WLED preset 1.

    Returns:
        bool: Success status
    """

def restore_last_state(self):
    """
    Restore previous known good state.

    Returns:
        bool: Success status
    """
```

#### Sequence Control

```python
def flash_sequence(self, flash_duration):
    """
    Execute green flashing sequence.

    Args:
        flash_duration (float): Sequence duration in seconds

    Returns:
        bool: True if completed, False if interrupted
    """

def stop_flashing(self):
    """
    Terminate current flash sequence.
    """
```

### Private Methods

```python
def _send_state(self, state):
    """
    Send state update to WLED with retry logic.

    Args:
        state (dict): State configuration

    Returns:
        bool: Success status
    """
```

## Utility Functions

### Logging Setup

```python
def setup_logging():
    """
    Configure rotating log system.

    Returns:
        logging.Logger: Configured logger instance
    """
```

### GPIO Management

```python
def cleanup():
    """
    Clean up GPIO resources on exit.
    """
```

## Main Program Flow

```python
def main():
    """
    Primary program execution flow.
    
    Sequence:
    1. Initialize logging system
    2. Create WLEDController instance
    3. Configure GPIO
    4. Establish WLED connection
    5. Set initial white state
    6. Configure button callback
    7. Enter monitoring loop
    8. Handle termination and cleanup
    """
```

## API Endpoints

The script interacts with WLED through two primary endpoints:

### Device Information
- **Endpoint**: `/json/info`
- **Method**: GET
- **Response**: Device configuration and capabilities

### State Control
- **Endpoint**: `/json/state`
- **Method**: POST
- **Payload Example**:
  ```json
  {
    "on": true,
    "bri": 255,
    "transition": 0,
    "seg": [{
      "id": 0,
      "col": [[0, 255, 0]],
      "fx": 0,
      "sx": 0,
      "ix": 0
    }]
  }
  ```

## Error Handling

### Network Errors
- Connection failures trigger automatic retry mechanism
- State preservation ensures recovery to known good state
- Rotating log captures error details and timestamps

### GPIO Errors
- Button debouncing prevents multiple triggers
- Resource cleanup on exit prevents GPIO conflicts
- Error logging for debugging

### State Errors
- Validation before state changes
- Automatic state restoration on failure
- Connection status tracking

## Logging System

### Configuration
- File location: `/var/log/wled_button.log`
- Maximum file size: 1MB
- Backup count: 5 files
- Format: `timestamp - level - message`

### Log Levels
- INFO: Normal operations
- WARNING: Recoverable issues
- ERROR: Critical problems

### Example Log Output
```
2025-01-11 10:15:23 - INFO - WLED Button Control Starting...
2025-01-11 10:15:24 - INFO - Connected to WLED Device
2025-01-11 10:15:24 - INFO - GPIO initialized on pin 18
2025-01-11 10:15:25 - INFO - Button detection enabled
2025-01-11 10:15:30 - INFO - Button press detected
```

This documentation provides a comprehensive reference for understanding and maintaining the WLED Button Controller script. For practical usage instructions, refer to the README.md file.
