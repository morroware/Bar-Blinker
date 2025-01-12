"""
WLED Button Controller for Raspberry Pi

Controls a WLED LED strip using a physical button. When pressed, flashes LEDs green
then returns to white. Features auto-reconnection and error recovery.

Hardware:
- Raspberry Pi (any model)
- Button on GPIO 18 to GND
- WLED device (ESP8266/ESP32)

Setup:
1. Connect button (GPIO 18 to GND)
2. Set WLED_IP to your device's IP
3. Run script
"""

import RPi.GPIO as GPIO
import requests
import time
import json
import logging
import logging.handlers
import os
import socket
from datetime import datetime

# Configuration
BUTTON_PIN = 18
WLED_IP = "192.168.1.100"
FLASH_DURATION = 30    # Seconds to flash
FLASH_INTERVAL = 0.5   # Seconds per flash cycle
FLASH_BRIGHTNESS = 255 # Flash brightness
LOG_FILE = "/var/log/wled_button.log"
MAX_RETRIES = 3
RETRY_DELAY = 1
RECONNECT_DELAY = 5
TRANSITION_TIME = 0.0  # No transition for sharp flashing

class WLEDController:
    def __init__(self, ip_address):
        self.ip_address = ip_address
        self.led_count = 0
        self.name = "Unknown"
        self.version = "Unknown"
        self.is_connected = False
        self._last_state = None
        self.flashing = False
        
    def wait_for_connection(self):
        """Continuously attempt to connect until successful"""
        attempt = 1
        while not self.is_connected:
            logging.info(f"Connection attempt {attempt}...")
            if self.initialize():
                return True
            attempt += 1
            time.sleep(RECONNECT_DELAY)
        return True

    def initialize(self):
        """Initialize connection and get device info"""
        info = self.get_info()
        if info:
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True
            logging.info(f"Connected to {self.name}, {self.led_count} LEDs")
            return True
        self.is_connected = False
        return False

    def get_info(self):
        """Get WLED device information"""
        try:
            response = requests.get(f"http://{self.ip_address}/json/info", timeout=5)
            return response.json() if response.status_code == 200 else None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED info: {e}")
            return None

    def set_color(self, red, green, blue, brightness=255):
        """Set color and brightness of all LEDs"""
        if not self.is_connected or self.led_count == 0:
            return False

        state = {
            "on": True,
            "bri": brightness,
            "transition": int(TRANSITION_TIME * 1000),
            "seg": [{
                "id": 0,
                "col": [[red, green, blue]],
                "fx": 0,
                "sx": 0,
                "ix": 0
            }]
        }
        
        success = self._send_state(state)
        if success:
            self._last_state = state
        return success

    def _send_state(self, state):
        """Send state update to WLED with retry logic"""
        url = f"http://{self.ip_address}/json/state"
        
        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(url, json=state, timeout=5)
                if response.status_code == 200:
                    return True
                logging.warning(f"Failed to set state (Attempt {attempt + 1})")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Error: {e}")
                self.is_connected = False
            
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        return False

    def flash_sequence(self, flash_duration):
        """Run green flashing sequence"""
        self.flashing = True
        start_time = time.time()
        flash_state = True
        
        try:
            while time.time() - start_time < flash_duration and self.flashing:
                if flash_state:
                    success = self.set_color(0, 255, 0, FLASH_BRIGHTNESS)
                else:
                    success = self.set_color(0, 0, 0, 0)
                    
                if not success:
                    self.flashing = False
                    return False
                    
                time.sleep(FLASH_INTERVAL / 2)
                flash_state = not flash_state
                
            self.flashing = False
            return True
            
        except Exception as e:
            logging.error(f"Flash sequence error: {e}")
            self.flashing = False
            return False

    def stop_flashing(self):
        """Stop current flash sequence"""
        self.flashing = False

    def restore_last_state(self):
        """Restore last known good state"""
        if self._last_state:
            logging.info("Restoring last state")
            return self._send_state(self._last_state)
        return False

    def save_state(self):
        """Save current state as WLED preset 1"""
        try:
            url = f"http://{self.ip_address}/json/state"
            response = requests.post(url, json={"ps": 1, "save": True}, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to save state: {e}")
            self.is_connected = False
            return False

def setup_logging():
    """Configure logging with rotation"""
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        return logger
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Logging setup failed: {e}")
        return logging.getLogger()

def cleanup():
    """Clean up GPIO resources"""
    try:
        GPIO.cleanup()
        logging.info("GPIO cleanup completed")
    except Exception as e:
        logging.error(f"Cleanup error: {e}")

def main():
    """Main program loop"""
    logger = setup_logging()
    logging.info("WLED Button Control Starting...")
    
    wled = WLEDController(WLED_IP)
    
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        logging.info(f"GPIO initialized on pin {BUTTON_PIN}")
        
        wled.wait_for_connection()
            
        if not wled.set_color(255, 255, 255):
            logging.error("Failed to set initial white color")
        
        if wled.save_state():
            logging.info("Saved initial state to preset 1")
        
        def button_callback(channel):
            """Handle button press: flash green then return to white"""
            try:
                logging.info("Button press detected")
                
                if not wled.is_connected and not wled.initialize():
                    logging.error("WLED device not connected")
                    return
                
                wled.stop_flashing()
                
                if wled.flash_sequence(FLASH_DURATION):
                    if not wled.set_color(255, 255, 255):
                        logging.error("Failed to restore white")
                        wled.restore_last_state()
                else:
                    logging.error("Flash sequence interrupted")
                    wled.restore_last_state()
                    
            except Exception as e:
                logging.error(f"Button callback error: {e}")
                wled.stop_flashing()
        
        GPIO.add_event_detect(
            BUTTON_PIN,
            GPIO.FALLING,
            callback=button_callback,
            bouncetime=300
        )
        logging.info("Button detection enabled")
        
        while True:
            if not wled.is_connected:
                logging.warning("Lost connection to WLED")
                wled.wait_for_connection()
                wled.restore_last_state()
            time.sleep(5)
            
    except KeyboardInterrupt:
        logging.info("Program stopped by user")
        wled.stop_flashing()
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
    finally:
        cleanup()

if __name__ == "__main__":
    main()
