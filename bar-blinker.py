#!/usr/bin/env python3
"""
A Flask-based Raspberry Pi WLED controller application
"""

import configparser
import os
import ipaddress
import time
import random
import logging
import logging.handlers
import threading
from threading import Lock
import socket
import RPi.GPIO as GPIO
import requests
from requests.auth import HTTPBasicAuth
from flask import Flask, request, render_template, redirect, url_for, jsonify
from functools import wraps
import hashlib
from datetime import datetime

# ======================
# Configuration Class
# ======================
class Config:
    """
    Holds all configuration variables for the WLED controller application.
    This class can load, validate, and write settings to an INI file.
    """

    BUTTON_PIN = 18
    WLED_IP = "192.168.1.15"
    LONG_PRESS_THRESHOLD = 3.0
    SHORT_FLASH_DURATION = 5.0
    FLASH_INTERVAL = 0.5
    FLASH_BRIGHTNESS = 255
    LOG_FILE = os.path.expanduser("/home/tech/wled_button.log")
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0
    RECONNECT_DELAY = 5.0
    TRANSITION_TIME = 0.0
    REQUEST_TIMEOUT = 5.0
    DEFAULT_MODE = "white"
    DEFAULT_EFFECT_INDEX = 162
    WLED_USERNAME = None
    WLED_PASSWORD = None

    # NEW: Speed & Intensity (0–255)
    DEFAULT_EFFECT_SPEED = 128
    DEFAULT_EFFECT_INTENSITY = 128

    # Rate-limiting 
    API_RATE_LIMIT = 100  # requests per minute
    SESSION_TIMEOUT = 3600  # 1 hour

    # Monitoring configurations
    HEALTH_CHECK_INTERVAL = 60  # seconds
    MAX_FAILED_ATTEMPTS = 5

    @classmethod
    def load_from_ini(cls, ini_path=None):
        """
        Loads configuration values from an INI file, if available.
        Fallbacks to default class attributes for any missing or invalid fields.
        """
        if ini_path:
            cls.INI_FILE_PATH = ini_path

        parser = configparser.ConfigParser()
        read_files = parser.read(cls.INI_FILE_PATH)
        if not read_files:
            logging.warning(f"Could not read config file: {cls.INI_FILE_PATH}. Using defaults.")

        section = "BLINKER"

        def get_str(key, default):
            return parser.get(section, key, fallback=str(default))

        def get_int(key, default):
            val_str = parser.get(section, key, fallback=str(default))
            try:
                return int(val_str)
            except ValueError:
                logging.warning(f"Invalid int for {key}: {val_str}. Using default={default}.")
                return default

        def get_float(key, default):
            val_str = parser.get(section, key, fallback=str(default))
            try:
                return float(val_str)
            except ValueError:
                logging.warning(f"Invalid float for {key}: {val_str}. Using default={default}.")
                return default

        def get_mode(key, default):
            val_str = parser.get(section, key, fallback=default)
            if val_str not in ["white", "effect"]:
                logging.warning(f"Invalid mode for {key}: {val_str}. Using default={default}.")
                return default
            return val_str

        # Load all configurations
        for attr in dir(cls):
            if not attr.startswith('_') and not callable(getattr(cls, attr)):
                value = getattr(cls, attr)
                if isinstance(value, bool):
                    setattr(cls, attr, parser.getboolean(section, attr, fallback=value))
                elif isinstance(value, int):
                    setattr(cls, attr, get_int(attr, value))
                elif isinstance(value, float):
                    setattr(cls, attr, get_float(attr, value))
                elif isinstance(value, str):
                    setattr(cls, attr, get_str(attr, value))

    @classmethod
    def validate(cls):
        """
        Validates that all configuration values are within acceptable ranges
        and the WLED_IP is a valid IP address.
        """
        try:
            # Enhanced IP validation
            try:
                socket.inet_aton(cls.WLED_IP)
            except socket.error:
                raise ValueError(f"Invalid IP address: {cls.WLED_IP}")

            # Validate numeric ranges
            if not (0 <= cls.FLASH_BRIGHTNESS <= 255):
                raise ValueError("Flash brightness must be between 0 and 255")
            
            if not (0 <= cls.BUTTON_PIN <= 27):
                raise ValueError("Invalid GPIO pin number")
            
            if cls.SHORT_FLASH_DURATION <= 0:
                raise ValueError("Short flash duration must be positive")
            
            if cls.FLASH_INTERVAL <= 0:
                raise ValueError("Flash interval must be positive")
            
            if cls.LONG_PRESS_THRESHOLD <= 0:
                raise ValueError("Long press threshold must be positive")
            
            if cls.DEFAULT_MODE not in ["white", "effect"]:
                raise ValueError("Invalid default mode")
            
            if not (0 <= cls.DEFAULT_EFFECT_INDEX <= 200):
                raise ValueError("Invalid effect index")

            # NEW checks: speed & intensity
            if not (0 <= cls.DEFAULT_EFFECT_SPEED <= 255):
                raise ValueError("Effect speed must be between 0 and 255")
            if not (0 <= cls.DEFAULT_EFFECT_INTENSITY <= 255):
                raise ValueError("Effect intensity must be between 0 and 255")

            # Validate file paths
            log_dir = os.path.dirname(cls.LOG_FILE)
            if log_dir and not os.access(log_dir, os.W_OK):
                raise ValueError(f"Log directory not writable: {log_dir}")

            return True
        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False

    @classmethod
    def write_to_ini(cls):
        parser = configparser.ConfigParser()
        section = "BLINKER"
        parser.add_section(section)

        # Write all non-private, non-callable attributes
        for attr in dir(cls):
            if not attr.startswith('_') and not callable(getattr(cls, attr)):
                value = getattr(cls, attr)
                if value is not None:
                    parser.set(section, attr, str(value))

        try:
            with open(cls.INI_FILE_PATH, "w") as config_file:
                parser.write(config_file)
        except Exception as e:
            logging.error(f"Failed to write configuration: {e}")
            raise


# ======================
# System Health Monitoring
# ======================
class SystemHealth:
    def __init__(self):
        self.last_successful_connection = None
        self.failed_attempts = 0
        self.button_press_count = 0
        self.last_error = None
        self.status = "initializing"
        self._lock = threading.Lock()

    def record_success(self):
        with self._lock:
            self.last_successful_connection = datetime.now()
            self.failed_attempts = 0
            self.status = "healthy"
            self.last_error = None

    def record_failure(self, error):
        with self._lock:
            self.failed_attempts += 1
            self.last_error = str(error)
            if self.failed_attempts >= Config.MAX_FAILED_ATTEMPTS:
                self.status = "critical"
            else:
                self.status = "degraded"

    def record_button_press(self):
        with self._lock:
            self.button_press_count += 1

    def get_status(self):
        with self._lock:
            return {
                "status": self.status,
                "last_successful_connection": (
                    self.last_successful_connection.isoformat() if self.last_successful_connection else None
                ),
                "failed_attempts": self.failed_attempts,
                "button_press_count": self.button_press_count,
                "last_error": self.last_error
            }


# ======================
# Logging Setup Function
# ======================
def setup_logging():
    try:
        log_dir = os.path.dirname(Config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=5
        )
        
        # Create console handler
        console_handler = logging.StreamHandler()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Set formatter for both handlers
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Get root logger and set level
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        logger.handlers = []
        
        # Add handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    except Exception as e:
        print(f"Failed to setup logging: {e}")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger()


# ======================
# WLED Controller Class
# ======================
class WLEDController:
    def __init__(self, ip_address, username=None, password=None):
        self.ip_address = ip_address
        self.username = username
        self.password = password
        self.led_count = 0
        self.name = "Unknown"
        self.version = "Unknown"
        self.is_connected = False
        self._last_state = None
        self._state_lock = Lock()
        self._flash_lock = Lock()
        self._flashing = False
        self._session = requests.Session()
        self._effects_cache = None
        self._effects_cache_time = None
        self._effects_cache_duration = 300  # 5 minutes
        self.system_health = SystemHealth()

        if self.username and self.password:
            self._session.auth = HTTPBasicAuth(self.username, self.password)

    @property
    def flashing(self):
        with self._flash_lock:
            return self._flashing

    @flashing.setter
    def flashing(self, value):
        with self._flash_lock:
            self._flashing = value

    def initialize(self):
        info = self.get_info()
        if info:
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True
            self.system_health.record_success()
            logging.info(f"Connected to {self.name} with {self.led_count} LEDs")
            return True
        self.is_connected = False
        return False

    def get_info(self):
        try:
            url = f"http://{self.ip_address}/json/info"
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                json_data = response.json()
                self.system_health.record_success()
                return json_data
            else:
                logging.error(f"Failed to get WLED info: HTTP {response.status_code}")
                self.system_health.record_failure(f"HTTP {response.status_code}")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED info: {e}")
            self.system_health.record_failure(str(e))
            return None
        except ValueError as e:
            logging.error(f"Invalid JSON response from WLED info: {e}")
            self.system_health.record_failure(str(e))
            return None

    def apply_effect(self, effect_index):
        """
        Applies an effect by index, using default brightness,
        speed, and intensity from Config.
        """
        try:
            url = f"http://{self.ip_address}/json/state"
            payload = {
                "on": True,
                "bri": Config.FLASH_BRIGHTNESS,
                "transition": int(Config.TRANSITION_TIME * 1000),
                "seg": [{
                    "id": 0,
                    "fx": effect_index,
                    "sx": Config.DEFAULT_EFFECT_SPEED,
                    "ix": Config.DEFAULT_EFFECT_INTENSITY
                }]
            }
            logging.debug(f"Applying effect {effect_index} with payload: {payload}")
            response = self._session.post(url, json=payload, timeout=Config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                logging.info(f"Applied effect {effect_index} (speed={Config.DEFAULT_EFFECT_SPEED}, intensity={Config.DEFAULT_EFFECT_INTENSITY}).")
                self.system_health.record_success()
                return True
            else:
                logging.error(f"Failed to apply effect {effect_index}: HTTP {response.status_code}")
                self.system_health.record_failure(f"HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to apply effect {effect_index}: {e}")
            self.system_health.record_failure(str(e))
            self.is_connected = False
            return False

    def auto_recover(self):
        if not self.is_connected:
            logging.info("Attempting auto-recovery of WLED connection...")
            if self.wait_for_connection():
                logging.info("Successfully reconnected to WLED")
                if self.restore_last_state():
                    logging.info("Successfully restored last state")
                    return True
                else:
                    logging.warning("Failed to restore last state after reconnection")
            else:
                logging.error("Failed to reconnect to WLED during auto-recovery")
        return False

    def get_health_status(self):
        return self.system_health.get_status()

    def cleanup(self):
        self.stop_flashing()
        self._session.close()
        logging.info("WLED controller cleanup completed")

    def wait_for_connection(self):
        attempt = 1
        max_delay = 60
        while not self.is_connected:
            logging.info(f"Connection attempt {attempt}...")
            if self.initialize():
                return True
            delay = min(Config.RECONNECT_DELAY * (2 ** (attempt - 1)), max_delay)
            jitter = delay * 0.1
            time.sleep(delay + (random.random() * jitter))
            attempt += 1
        return True

    def set_color(self, r, g, b, brightness=255):
        if not self.is_connected or self.led_count == 0:
            return False
        state = {
            "on": True,
            "bri": brightness,
            "transition": int(Config.TRANSITION_TIME * 1000),
            "seg": [{
                "id": 0,
                "col": [[r, g, b]],
                "fx": 0,
                "sx": 0,
                "ix": 0
            }]
        }
        return self._send_state(state)

    def _send_state(self, state):
        url = f"http://{self.ip_address}/json/state"
        for attempt in range(Config.MAX_RETRIES):
            try:
                resp = self._session.post(url, json=state, timeout=Config.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    with self._state_lock:
                        self._last_state = state
                    self.system_health.record_success()
                    return True
                logging.warning(f"Failed to set WLED state (Attempt {attempt+1}): HTTP {resp.status_code}")
                self.system_health.record_failure(f"HTTP {resp.status_code}")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Request error: {e}")
                self.system_health.record_failure(str(e))
                self.is_connected = False

            if attempt < Config.MAX_RETRIES - 1:
                time.sleep(Config.RETRY_DELAY * (2 ** attempt))
        return False

    def stop_flashing(self):
        self.flashing = False

    def restore_last_state(self):
        with self._state_lock:
            if self._last_state:
                logging.info("Restoring last known WLED state")
                return self._send_state(self._last_state)
        return False

    def set_white(self):
        logging.info("Setting LEDs to white.")
        return self.set_color(255, 255, 255, Config.FLASH_BRIGHTNESS)

    def get_effects(self):
        current_time = time.time()
        
        # Return cached effects if still valid
        if (self._effects_cache is not None and 
            self._effects_cache_time is not None and 
            current_time - self._effects_cache_time < self._effects_cache_duration):
            return self._effects_cache

        try:
            url = f"http://{self.ip_address}/json"
            logging.debug(f"Fetching effects from {url}")
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)
            
            if response.status_code == 200:
                json_data = response.json()
                effects = json_data.get('effects', [])
                logging.info(f"Retrieved {len(effects)} effects from WLED")

                # Update cache
                self._effects_cache = effects
                self._effects_cache_time = current_time
                self.system_health.record_success()
                return effects
            else:
                logging.error(f"Failed to get WLED effects: HTTP {response.status_code}")
                self.system_health.record_failure(f"HTTP {response.status_code}")
                return self._effects_cache if self._effects_cache else []
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED effects: {e}")
            self.system_health.record_failure(str(e))
            return self._effects_cache if self._effects_cache else []
        except ValueError as e:
            logging.error(f"Invalid JSON response from WLED effects: {e}")
            self.system_health.record_failure(str(e))
            return self._effects_cache if self._effects_cache else []


# =================================
# Helper: Revert to user-selected default
# =================================
def revert_to_user_default(wled: 'WLEDController'):
    logging.info("Reverting to user default...")
    if Config.DEFAULT_MODE == "white":
        wled.set_white()
    else:
        wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

# ======================
# Blink Red Alert
# ======================
def blink_red_alert(wled: 'WLEDController'):
    logging.info("Issuing red alert due to incomplete long press.")
    start_time = time.time()
    flash_state = True
    wled.flashing = True

    try:
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            interval = Config.FLASH_INTERVAL / 2
            if flash_state:
                if not wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS):
                    logging.error("Failed to set red color during alert")
                    wled.auto_recover()
            else:
                if not wled.set_color(0, 0, 0, 0):
                    logging.error("Failed to set off state during alert")
                    wled.auto_recover()
            flash_state = not flash_state
            time.sleep(interval)
        revert_to_user_default(wled)
    except Exception as e:
        logging.error(f"Error during red alert blinking: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Blink Green (Short Press)
# ======================
def blink_green_for_30s(wled: 'WLEDController'):
    import RPi.GPIO as GPIO

    logging.info("Short press => blink 'blue' for up to SHORT_FLASH_DURATION seconds")
    wled.system_health.record_button_press()

    start_time = time.time()
    flash_state = True
    wled.flashing = True

    press_start_time = None
    long_press_active = False
    long_press_initiated = False

    try:
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            # Check for button press
            if GPIO.input(Config.BUTTON_PIN) == 0:
                if press_start_time is None:
                    press_start_time = time.time()
                elif (time.time() - press_start_time) >= Config.LONG_PRESS_THRESHOLD and not long_press_active:
                    logging.info("Long press detected during blue => switching to red immediately")
                    long_press_active = True
                    long_press_initiated = True
                    while GPIO.input(Config.BUTTON_PIN) == 0 and wled.flashing:
                        interval = Config.FLASH_INTERVAL / 2
                        if flash_state:
                            if not wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS):
                                wled.auto_recover()
                        else:
                            if not wled.set_color(0, 0, 0, 0):
                                wled.auto_recover()
                        flash_state = not flash_state
                        time.sleep(interval)
                    revert_to_user_default(wled)
                    return
            else:
                press_start_time = None

            # Flash blue
            interval = Config.FLASH_INTERVAL / 2
            if flash_state:
                if not wled.set_color(0, 0, 255, Config.FLASH_BRIGHTNESS):
                    wled.auto_recover()
            else:
                if not wled.set_color(0, 0, 0, 0):
                    wled.auto_recover()
            flash_state = not flash_state
            time.sleep(interval)

        revert_to_user_default(wled)

        if long_press_initiated:
            logging.info("Long press was initiated during blue flashing but not completed. Triggering red alert.")
            blink_red_alert(wled)

    except Exception as e:
        logging.error(f"Error during blink sequence: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Simulate Short Press
# ======================
def simulate_short_press(wled: 'WLEDController'):
    logging.info("Simulating short press from web UI.")
    wled.stop_flashing()
    blink_green_for_30s(wled)

# ======================
# Simulate Long Press
# ======================
def simulate_long_press(wled: 'WLEDController'):
    import RPi.GPIO as GPIO
    logging.info("Simulating long press from web UI.")
    wled.system_health.record_button_press()

    wled.stop_flashing()

    hold_start = time.time()
    wled.flashing = True
    blinking_red = True
    blink_state = False
    last_blink_time = time.time()

    try:
        while blinking_red and wled.flashing:
            threshold = Config.LONG_PRESS_THRESHOLD
            interval = Config.FLASH_INTERVAL / 2

            if (time.time() - hold_start) >= threshold:
                blinking_red = False
                revert_to_user_default(wled)
                logging.info("Simulated long press release => reverting to default")
                break

            now = time.time()
            if (now - last_blink_time) >= interval:
                if blink_state:
                    if not wled.set_color(0, 0, 0, 0):
                        wled.auto_recover()
                else:
                    if not wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS):
                        wled.auto_recover()
                blink_state = not blink_state
                last_blink_time = now

            time.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during long press simulation: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Hardware Button Loop
# ======================
def hardware_button_loop(wled: 'WLEDController', stop_event: threading.Event):
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(Config.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Apply initial mode
    if Config.DEFAULT_MODE == "white":
        wled.set_white()
    elif Config.DEFAULT_MODE == "effect":
        wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

    pressed = False
    press_start_time = 0.0
    blinking_red = False
    blink_state = False
    last_blink_time = 0.0

    while not stop_event.is_set():
        if not wled.is_connected:
            logging.warning("Lost connection to WLED; attempting reconnect from hardware loop...")
            if wled.auto_recover():
                logging.info("Successfully recovered WLED connection")
            else:
                logging.error("Failed to recover WLED connection")
                time.sleep(Config.RECONNECT_DELAY)
                continue

        current_state = GPIO.input(Config.BUTTON_PIN)

        if not pressed:
            if current_state == 0:
                pressed = True
                press_start_time = time.time()
                blinking_red = False
                wled.stop_flashing()
        else:
            if current_state == 1:
                duration = time.time() - press_start_time
                pressed = False

                if blinking_red:
                    logging.info("Long press released => revert to default")
                    revert_to_user_default(wled)
                    blinking_red = False
                else:
                    threshold = Config.LONG_PRESS_THRESHOLD
                    if duration < threshold:
                        blink_green_for_30s(wled)
                    else:
                        logging.info("Long press ended without in-press blinking => blink red now.")
                        blink_red_alert(wled)
            else:
                held_duration = time.time() - press_start_time
                threshold = Config.LONG_PRESS_THRESHOLD
                if (held_duration >= threshold) and not blinking_red:
                    logging.info("Long press threshold reached => blinking red while held down")
                    blinking_red = True
                    blink_state = False
                    last_blink_time = time.time()

                if blinking_red:
                    interval = Config.FLASH_INTERVAL / 2
                    now = time.time()
                    if (now - last_blink_time) >= interval:
                        if blink_state:
                            if not wled.set_color(0, 0, 0, 0):
                                wled.auto_recover()
                        else:
                            if not wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS):
                                wled.auto_recover()
                        blink_state = not blink_state
                        last_blink_time = now

        time.sleep(0.01)

    GPIO.cleanup()
    logging.info("Hardware button loop exiting...")

# ======================
# Rate Limit Decorator
# ======================
def rate_limit(f):
    """
    Limits each IP to Config.API_RATE_LIMIT requests per minute.
    """
    requests_per_ip = {}

    @wraps(f)
    def decorated(*args, **kwargs):
        now = time.time()
        ip = request.remote_addr
        
        # Clean old requests older than 60 seconds
        for k, v in list(requests_per_ip.items()):
            requests_per_ip[k] = [ts for ts in v if ts > now - 60]
        
        if ip not in requests_per_ip:
            requests_per_ip[ip] = []
        if len(requests_per_ip[ip]) >= Config.API_RATE_LIMIT:
            return jsonify({"error": "Rate limit exceeded"}), 429
        
        requests_per_ip[ip].append(now)
        return f(*args, **kwargs)
    return decorated

# ======================
# Flask Setup (No CSRF)
# ======================
app = Flask(__name__)
stop_event = threading.Event()
wled = None  # Will be initialized in main()

# NO before_request for CSRF, no CSRF decorator

@app.route("/")
@rate_limit
def index():
    if not wled.is_connected:
        logging.warning("WLED not connected. Effects will not be available.")
        effects = []
    else:
        effects = wled.get_effects()
    
    current_effect = Config.DEFAULT_EFFECT_INDEX if Config.DEFAULT_MODE == "effect" else None
    current_mode = Config.DEFAULT_MODE
    health_status = wled.get_health_status()
    
    logging.info(f"Rendering index with mode={current_mode}, effect_index={current_effect}")
    
    return render_template(
        "index.html",
        c=Config,
        effects=effects,
        current_mode=current_mode,
        current_effect=current_effect,
        health_status=health_status
    )

@app.route("/update_config", methods=["POST"])
@rate_limit
def update_config():
    """
    Update WLED configuration settings from a form (no CSRF).
    Includes effect speed/intensity, IP address, brightness, etc.
    """
    try:
        form = request.form

        # Validate IP address
        new_ip = form.get("WLED_IP", Config.WLED_IP)
        try:
            socket.inet_aton(new_ip)
            Config.WLED_IP = new_ip
        except socket.error:
            return jsonify({"error": "Invalid IP address"}), 400

        def update_numeric(key, min_val=None, max_val=None, is_int=False):
            if key in form:
                try:
                    val = int(form[key]) if is_int else float(form[key])
                    if (min_val is not None and val < min_val) or \
                       (max_val is not None and val > max_val):
                        raise ValueError
                    setattr(Config, key, val)
                except ValueError:
                    return False
            return True

        # Update numeric fields
        validations = [
            update_numeric("LONG_PRESS_THRESHOLD", min_val=0.1),
            update_numeric("SHORT_FLASH_DURATION", min_val=0.1),
            update_numeric("FLASH_INTERVAL", min_val=0.1),
            update_numeric("FLASH_BRIGHTNESS", min_val=0, max_val=255, is_int=True),
            update_numeric("MAX_RETRIES", min_val=1, is_int=True),
            update_numeric("RETRY_DELAY", min_val=0.1),
            update_numeric("RECONNECT_DELAY", min_val=0.1),
            update_numeric("TRANSITION_TIME", min_val=0),
            update_numeric("REQUEST_TIMEOUT", min_val=0.1),
            update_numeric("DEFAULT_EFFECT_SPEED", min_val=0, max_val=255, is_int=True),
            update_numeric("DEFAULT_EFFECT_INTENSITY", min_val=0, max_val=255, is_int=True)
        ]

        if not all(validations):
            return jsonify({"error": "Invalid numeric parameters"}), 400

        # Update string fields
        Config.LOG_FILE = form.get("LOG_FILE", Config.LOG_FILE)
        Config.WLED_USERNAME = form.get("WLED_USERNAME", Config.WLED_USERNAME)
        Config.WLED_PASSWORD = form.get("WLED_PASSWORD", Config.WLED_PASSWORD)

        # Update Mode and Effect Selection
        selected_mode = form.get("mode", Config.DEFAULT_MODE)
        if selected_mode not in ["white", "effect"]:
            return jsonify({"error": "Invalid mode selected"}), 400
        Config.DEFAULT_MODE = selected_mode

        if selected_mode == "effect":
            try:
                effect_index = int(form.get("effect_index", Config.DEFAULT_EFFECT_INDEX))
                Config.DEFAULT_EFFECT_INDEX = effect_index
            except ValueError:
                return jsonify({"error": "Invalid effect index"}), 400

        # Write to INI
        Config.write_to_ini()
        logging.info("Updated configuration from web UI")

        # Apply the selected mode immediately
        if selected_mode == "white":
            wled.set_white()
        elif selected_mode == "effect":
            wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

        return redirect(url_for("index"))
    except Exception as e:
        logging.error(f"Error updating configuration: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/simulate_press", methods=["POST"])
@rate_limit
def simulate_press():
    press_type = request.form.get("press_type")
    if press_type == "short":
        simulate_short_press(wled)
    elif press_type == "long":
        simulate_long_press(wled)
    else:
        logging.warning(f"Unknown press type: {press_type}")
        return jsonify({"error": "Invalid press type"}), 400
    return redirect(url_for("index"))

@app.route("/health", methods=["GET"])
@rate_limit
def health_check():
    return jsonify(wled.get_health_status())

# Background connection thread
def background_connect_wled(wled: 'WLEDController', stop_event: threading.Event):
    try:
        while not stop_event.is_set():
            if not wled.is_connected:
                wled.wait_for_connection()
            time.sleep(Config.HEALTH_CHECK_INTERVAL)
    except Exception as e:
        logging.error(f"Error in background_connect_wled: {e}")

def main():
    try:
        # Load and validate configuration
        Config.load_from_ini("blinker-configs.ini")
        setup_logging()
        if not Config.validate():
            logging.error("Invalid configuration; exiting.")
            return

        logging.info("Starting WLED Button Flask Application...")

        # Initialize WLED controller
        global wled
        wled = WLEDController(
            Config.WLED_IP,
            username=Config.WLED_USERNAME,
            password=Config.WLED_PASSWORD
        )

        # Start background threads
        global stop_event
        connect_thread = threading.Thread(
            target=background_connect_wled,
            args=(wled, stop_event),
            daemon=True
        )
        connect_thread.start()

        hardware_thread = threading.Thread(
            target=hardware_button_loop,
            args=(wled, stop_event),
            daemon=True
        )
        hardware_thread.start()

        # Apply initial mode
        if Config.DEFAULT_MODE == "white":
            wled.set_white()
        elif Config.DEFAULT_MODE == "effect":
            wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

        # Start Flask app
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

    except Exception as e:
        logging.error(f"Error in main: {e}")
    finally:
        stop_event.set()
        if 'connect_thread' in locals():
            connect_thread.join()
        if 'hardware_thread' in locals():
            hardware_thread.join()
        if 'wled' in globals() and wled is not None:
            wled.cleanup()

if __name__ == "__main__":
    stop_event = threading.Event()
    main()

