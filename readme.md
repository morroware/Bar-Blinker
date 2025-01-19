# Bar-Blinker RGBW

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![WLED Compatible](https://img.shields.io/badge/WLED-Compatible-brightgreen.svg)](https://github.com/Aircoookie/WLED)

Raspberry Pi WLED controller implementing GPIO input monitoring for RGBW LED control. Features thread-safe operation, exponential backoff reconnection, health monitoring, and web configuration.

## System Architecture

### Threading Implementation
1. Main Thread (Flask Web Server)
   - Handles HTTP requests on port 5000
   - Implements rate limiting via IP tracking
   - Manages configuration updates
   - Provides health status endpoint
   - Uses thread-safe session management

2. Hardware Thread
   - Monitors GPIO pin state (default: GPIO18)
   - Implements software debounce
   - Tracks press durations with microsecond precision
   - Controls LED state transitions
   - Manages auto-recovery on connection loss

3. Connection Thread
   - Maintains WLED device connection
   - Implements exponential backoff (max 60s)
   - Adds random jitter (±10% of delay)
   - Caches effect lists for 300s
   - Monitors connection health

### State Machine
1. Input States
   ```
   IDLE → SHORT_PRESS → SEQUENCE_ACTIVE → IDLE
                     ↘ LONG_PRESS → ALERT_ACTIVE → IDLE
   ```

2. LED States
   ```
   DEFAULT_WHITE (0,0,0,255) →
      SHORT_PRESS: BLUE (0,0,255,0) ↔ WHITE (0,0,0,255)
      LONG_PRESS: RED (255,0,0,0) ↔ OFF (0,0,0,0)
   ```

3. Connection States
   ```
   INITIALIZING → HEALTHY ↔ DEGRADED → CRITICAL
   ```

### Resource Management
1. Thread Synchronization
   - State Lock: `_state_lock`
   - Flash Lock: `_flash_lock`
   - Health Lock: `_lock`
   - Rate Limit Locks

2. Memory Management
   - Effect Caching
   - Session Management
   - Request Rate Tracking
   - State History

## Technical Implementation

### GPIO Configuration
```python
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
```
- Active-low logic
- Internal pull-up enabled
- 10ms polling interval
- Software debounce implementation

### WLED Communication
1. Base URI: `http://{WLED_IP}/json/`
2. Endpoints:
   ```
   /state  - POST JSON state updates
   /info   - GET device information
   /       - GET effect list
   ```
3. State JSON Structure:
   ```json
   {
     "on": true,
     "bri": 0-255,
     "transition": milliseconds,
     "seg": [{
       "id": 0,
       "col": [[r,g,b,w]],
       "fx": effect_index,
       "sx": speed,
       "ix": intensity
     }]
   }
   ```

### Error Handling
1. Connection Failures
   ```python
   for attempt in range(MAX_RETRIES):
       delay = RETRY_DELAY * (2 ** attempt)
       jitter = random.random() * (delay * 0.1)
       time.sleep(delay + jitter)
   ```

2. State Recovery
   ```python
   if not self.is_connected:
       self.wait_for_connection()
       self.restore_last_state()
   ```

### Health Monitoring
1. Metrics Tracked:
   ```python
   {
     "status": ["healthy", "degraded", "critical"],
     "last_successful_connection": ISO8601,
     "failed_attempts": int,
     "button_press_count": int,
     "last_error": str
   }
   ```

2. Status Transitions:
   - healthy → degraded: Single connection failure
   - degraded → critical: MAX_FAILED_ATTEMPTS reached
   - any → healthy: Successful connection

## Configuration Parameters

### System Configuration
```ini
[BLINKER]
BUTTON_PIN = 18                  # GPIO BCM mode pin
WLED_IP = "192.168.1.15"        # IPv4 address
LONG_PRESS_THRESHOLD = 3.0       # Seconds
SHORT_FLASH_DURATION = 5.0       # Seconds
FLASH_INTERVAL = 0.5            # Seconds
FLASH_BRIGHTNESS = 255          # 0-255
TRANSITION_TIME = 0.0           # Seconds
REQUEST_TIMEOUT = 5.0           # Seconds
```

### Network Parameters
```ini
MAX_RETRIES = 3                 # Per request
RETRY_DELAY = 1.0              # Base seconds
RECONNECT_DELAY = 5.0          # Base seconds
API_RATE_LIMIT = 100           # Requests per minute
SESSION_TIMEOUT = 3600         # Seconds
```

### Effect Configuration
```ini
DEFAULT_MODE = "white"          # "white" or "effect"
DEFAULT_EFFECT_INDEX = 162      # 0-200
DEFAULT_EFFECT_SPEED = 128      # 0-255
DEFAULT_EFFECT_INTENSITY = 128  # 0-255
```

### Authentication
```ini
WLED_USERNAME = null           # Optional HTTP Basic Auth
WLED_PASSWORD = null           # Optional HTTP Basic Auth
```

## HTTP API

### Rate-Limited Endpoints
Rate limit: 100 requests per minute per IP
```python
@app.route("/")
@rate_limit
def index():
    return render_template("index.html", ...)
```

### Configuration Updates
```http
POST /update_config
Content-Type: application/x-www-form-urlencoded

WLED_IP=192.168.1.15&LONG_PRESS_THRESHOLD=3.0...
```

### Input Simulation
```http
POST /simulate_press
Content-Type: application/x-www-form-urlencoded

press_type=short|long
```

### Health Check
```http
GET /health
Response: application/json

{
  "status": "healthy",
  "last_successful_connection": "2024-01-19T10:00:00Z",
  "failed_attempts": 0,
  "button_press_count": 42,
  "last_error": null
}
```

## Installation

### Dependencies
```bash
# System packages
apt-get install -y python3-pip python3-venv

# Python packages
pip install flask>=2.0.0 requests>=2.25.1 RPi.GPIO>=0.7.0
```

### Systemd Service
```ini
[Unit]
Description=Bar-Blinker RGBW Controller
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/main.py
WorkingDirectory=/path/to/
User=pi
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### File Permissions
```bash
chmod 644 /etc/systemd/system/bar-blinker.service
chmod 755 /path/to/main.py
chown -R pi:pi /path/to/
```

## Logging

### Configuration
- Handler: RotatingFileHandler
- Max Size: 1MB
- Backup Count: 5
- Format: `%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s`
- Date Format: `%Y-%m-%d %H:%M:%S`

### Log Locations
1. Application Log
   ```
   /home/tech/wled_button.log
   ```
2. Systemd Journal
   ```bash
   journalctl -u bar-blinker -f
   ```

## Error Codes and Recovery

### HTTP Status Codes
- 200: Success
- 400: Invalid configuration
- 429: Rate limit exceeded
- 500: Internal server error

### Recovery Methods
1. Connection Loss
   ```python
   while not self.is_connected:
       if self.initialize():
           self.restore_last_state()
           return True
       time.sleep(backoff_delay)
   ```

2. State Corruption
   ```python
   def auto_recover(self):
       if self.wait_for_connection():
           return self.restore_last_state()
       return False
   ```

### Critical Errors
1. GPIO Access Failure
   - Requires service restart
   - Check permissions
   - Verify hardware connections

2. Configuration Corruption
   - Reload from INI file
   - Fall back to defaults
   - Validate all parameters

3. Network Failure
   - Implement exponential backoff
   - Cache last known state
   - Return to default state

## License
MIT License - See LICENSE file for details
