#!/usr/bin/env python3
"""
A Flask-based Raspberry Pi WLED controller application with hardware button support.

Features:
    - Short press: Blinks "blue" (we often refer to it as "green" in the code doc, but the actual color is blue: (0,0,255)) for up to Config.SHORT_FLASH_DURATION seconds.
    - Long press: Blinks red (255,0,0) until the long press is released, then reverts to the user's default mode.
    - A long press can override an ongoing short press blink sequence (blue).
    - At the end of any blinking sequence (short or long), WLED reverts to the user-selected default mode (white or specified effect).
    - REST endpoints to simulate button presses, update configuration, view health/status, and more.

This script demonstrates:
    1) Using a physical button on GPIO pin (Config.BUTTON_PIN) to initiate color blinking.
    2) Automatic reversion to a default state (white or effect).
    3) Simple concurrency with threads (hardware button loop, background connection checks, and the Flask web server).
    4) Rate-limited API endpoints, basic config management (INI file), and system health tracking.
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

    Class Attributes:
        BUTTON_PIN (int): The GPIO pin number for the hardware button.
        WLED_IP (str): IP address for the WLED device.
        LONG_PRESS_THRESHOLD (float): Time in seconds to hold a button press to be considered "long."
        SHORT_FLASH_DURATION (float): Duration in seconds for the short-press (blue blink) sequence.
        FLASH_INTERVAL (float): Interval (in seconds) at which blink toggles on/off.
        FLASH_BRIGHTNESS (int): Brightness to use during blink sequences (0-255).
        LOG_FILE (str): File path for log output.
        MAX_RETRIES (int): Max attempts for WLED state changes before giving up.
        RETRY_DELAY (float): Delay (in seconds) between state-change retries.
        RECONNECT_DELAY (float): Delay (in seconds) for reconnect attempts to WLED, doubled after each failure.
        TRANSITION_TIME (float): Transition time for color changes (in seconds).
        REQUEST_TIMEOUT (float): Timeout (in seconds) for WLED network requests.
        DEFAULT_MODE (str): The default mode after any blink. Should be "white" or "effect".
        DEFAULT_EFFECT_INDEX (int): The WLED effect index to use if DEFAULT_MODE is "effect".
        WLED_USERNAME (str or None): Username for WLED HTTP Basic Auth (if any).
        WLED_PASSWORD (str or None): Password for WLED HTTP Basic Auth (if any).
        DEFAULT_EFFECT_SPEED (int): Default effect speed for WLED (0–255).
        DEFAULT_EFFECT_INTENSITY (int): Default effect intensity for WLED (0–255).
        API_RATE_LIMIT (int): Allowed number of API requests per IP address per minute.
        SESSION_TIMEOUT (int): Session timeout in seconds.
        HEALTH_CHECK_INTERVAL (int): Interval in seconds for checking WLED health in the background thread.
        MAX_FAILED_ATTEMPTS (int): Max consecutive failed attempts for certain WLED requests before status is "critical".
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

    DEFAULT_EFFECT_SPEED = 128
    DEFAULT_EFFECT_INTENSITY = 128

    API_RATE_LIMIT = 100  # requests per minute
    SESSION_TIMEOUT = 3600  # 1 hour

    HEALTH_CHECK_INTERVAL = 60  # seconds
    MAX_FAILED_ATTEMPTS = 5

    INI_FILE_PATH = "blinker-configs.ini"  # default path (can be overridden)

    @classmethod
    def load_from_ini(cls, ini_path=None):
        """
        Loads configuration values from an INI file, if available.
        Fallbacks to default class attributes for any missing or invalid fields.

        Args:
            ini_path (str, optional): Custom path to an INI file.
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

        # Load each existing class attribute from the INI, if present
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
                    if attr == "DEFAULT_MODE":
                        setattr(cls, attr, get_mode(attr, value))
                    else:
                        setattr(cls, attr, get_str(attr, value))

    @classmethod
    def validate(cls):
        """
        Validates that all configuration values are within acceptable ranges
        and that WLED_IP is a valid IP address. Logs errors on invalid config.

        Returns:
            bool: True if config is valid, False otherwise.
        """
        try:
            # Validate IP address
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

            # Validate log file path
            log_dir = os.path.dirname(cls.LOG_FILE)
            if log_dir and not os.access(log_dir, os.W_OK):
                raise ValueError(f"Log directory not writable: {log_dir}")

            return True

        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False

    @classmethod
    def write_to_ini(cls):
        """
        Writes the current class attributes to the INI file for persistence.
        """
        parser = configparser.ConfigParser()
        section = "BLINKER"
        parser.add_section(section)

        # Write all non-private, non-callable attributes to the INI
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
    """
    Tracks various system health metrics, including:
    - Last successful connection time
    - Number of consecutive failed attempts
    - Number of button presses
    - Last error message
    - Overall status level: "initializing", "healthy", "degraded", or "critical"
    """

    def __init__(self):
        self.last_successful_connection = None
        self.failed_attempts = 0
        self.button_press_count = 0
        self.last_error = None
        self.status = "initializing"
        self._lock = threading.Lock()

    def record_success(self):
        """
        Resets the failure count, updates last_successful_connection,
        and sets status back to 'healthy'.
        """
        with self._lock:
            self.last_successful_connection = datetime.now()
            self.failed_attempts = 0
            self.status = "healthy"
            self.last_error = None

    def record_failure(self, error):
        """
        Increments the failure count, updates last_error, and sets status
        to 'degraded' or 'critical' if MAX_FAILED_ATTEMPTS is reached.
        """
        with self._lock:
            self.failed_attempts += 1
            self.last_error = str(error)
            if self.failed_attempts >= Config.MAX_FAILED_ATTEMPTS:
                self.status = "critical"
            else:
                self.status = "degraded"

    def record_button_press(self):
        """
        Increments the button press counter (for debugging or analytics).
        """
        with self._lock:
            self.button_press_count += 1

    def get_status(self):
        """
        Returns a dictionary of current system health info.
        """
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
    """
    Sets up the application-wide logging with both rotating file handler
    and console output handler. If file setup fails, it defaults to basicConfig.

    Returns:
        logging.Logger: Configured logger for the root namespace.
    """
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
    """
    Encapsulates network interactions with a WLED device, including:
    - Checking connectivity and retrieving info (get_info).
    - Applying color or effect states (set_color, apply_effect).
    - Caching effects data to avoid repeated requests.
    - Handling reconnection attempts and storing the last known state.
    """

    def __init__(self, ip_address, username=None, password=None):
        """
        Initializes a WLEDController instance.

        Args:
            ip_address (str): IP address of the WLED device.
            username (str, optional): HTTP Basic Auth username.
            password (str, optional): HTTP Basic Auth password.
        """
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
        """
        A thread-safe flag indicating if the controller is currently in a
        blinking (flash) state (short-press or long-press alert).
        """
        with self._flash_lock:
            return self._flashing

    @flashing.setter
    def flashing(self, value):
        with self._flash_lock:
            self._flashing = value

    def initialize(self):
        """
        Attempts to connect to WLED and retrieve basic info (name, version, LED count).

        Returns:
            bool: True if connection was successful, False otherwise.
        """
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
        """
        Retrieves /json/info from the WLED device.

        Returns:
            dict or None: JSON data if successful, otherwise None.
        """
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

        Args:
            effect_index (int): The WLED effect index to apply.

        Returns:
            bool: True if successful, otherwise False.
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
        """
        Attempts to automatically recover if WLED is disconnected.

        Returns:
            bool: True if reconnection (and state restoration) succeeded, False otherwise.
        """
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
        """
        Retrieves system health metrics from the internal SystemHealth object.

        Returns:
            dict: System health info (status, last_successful_connection, etc.).
        """
        return self.system_health.get_status()

    def cleanup(self):
        """
        Stops any ongoing flashing and closes the network session.
        """
        self.stop_flashing()
        self._session.close()
        logging.info("WLED controller cleanup completed")

    def wait_for_connection(self):
        """
        Repeatedly tries to initialize() the WLEDController until successful or stopped.

        Returns:
            bool: True if eventually connected, False if interrupted or failed.
        """
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
        """
        Sets the color of the WLED strip to a specific (r,g,b) with the given brightness.

        Args:
            r (int): Red component (0–255).
            g (int): Green component (0–255).
            b (int): Blue component (0–255).
            brightness (int): Brightness (0–255).

        Returns:
            bool: True if successful, False otherwise.
        """
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
        """
        Internal helper to POST a given JSON state to WLED, with retries.

        Args:
            state (dict): A JSON-serializable dict representing the WLED state payload.

        Returns:
            bool: True if successfully set, False if all retries failed.
        """
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
        """
        Sets the flashing flag to False, indicating that any ongoing blink sequences
        should terminate gracefully.
        """
        self.flashing = False

    def restore_last_state(self):
        """
        Attempts to re-apply the last known WLED state stored in self._last_state.

        Returns:
            bool: True if successfully restored, False otherwise.
        """
        with self._state_lock:
            if self._last_state:
                logging.info("Restoring last known WLED state")
                return self._send_state(self._last_state)
        return False

    def set_white(self):
        """
        Convenience method to set the WLED strip to full white at FLASH_BRIGHTNESS.
        """
        logging.info("Setting LEDs to white.")
        return self.set_color(255, 255, 255, Config.FLASH_BRIGHTNESS)

    def get_effects(self):
        """
        Retrieves the list of WLED's available effects from /json. Results are cached for 5 minutes.

        Returns:
            list: List of effect names (strings).
        """
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
    """
    Reverts WLED to the user-chosen default, either white or a specified effect.
    """
    logging.info("Reverting to user default...")
    if Config.DEFAULT_MODE == "white":
        wled.set_white()
    else:
        wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)


# ======================
# Blink Red Alert
# ======================
def blink_red_alert(wled: 'WLEDController'):
    """
    Blink red for up to SHORT_FLASH_DURATION seconds, typically triggered by
    a completed long press or partial/accidental long press.

    Args:
        wled (WLEDController): WLED controller instance to manipulate.
    """
    logging.info("Issuing red alert due to incomplete or normal long press.")
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

        # Normal exit => revert
        revert_to_user_default(wled)

    except Exception as e:
        logging.error(f"Error during red alert blinking: {e}")
        # On exception => revert as well
        revert_to_user_default(wled)
    finally:
        # Always clear the flashing flag
        wled.flashing = False


# ======================
# Blink Green (Short Press) [Actually blue color in code]
# ======================
def blink_green_for_30s(wled: 'WLEDController'):
    """
    Blink 'blue' for up to SHORT_FLASH_DURATION seconds, triggered by a short press.
    If a new long press is detected during the blue blinking, override with red blinking
    just like a normal long press.

    Args:
        wled (WLEDController): WLED controller instance to manipulate.
    """
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
            # Check if the user is pressing the button again during the short-press (blue) sequence
            if GPIO.input(Config.BUTTON_PIN) == 0:
                if press_start_time is None:
                    press_start_time = time.time()
                # If pressed long enough to qualify as a new long press, override the blue with red
                elif (time.time() - press_start_time) >= Config.LONG_PRESS_THRESHOLD and not long_press_active:
                    logging.info("Long press detected during blue => switching to red immediately")
                    long_press_active = True
                    long_press_initiated = True

                    # Blink red as long as the button remains pressed
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

                    # Revert before returning
                    revert_to_user_default(wled)
                    return
            else:
                # If the button is not pressed, reset press_start_time
                press_start_time = None

            # Continue blinking blue
            interval = Config.FLASH_INTERVAL / 2
            if flash_state:
                if not wled.set_color(0, 0, 255, Config.FLASH_BRIGHTNESS):  # Blue color
                    wled.auto_recover()
            else:
                if not wled.set_color(0, 0, 0, 0):
                    wled.auto_recover()
            flash_state = not flash_state
            time.sleep(interval)

        # If we exit the loop normally, revert
        revert_to_user_default(wled)

        # If a new long press was initiated but not completed for some reason, do a red alert
        if long_press_initiated:
            logging.info("Long press was initiated during blue flashing but not completed. Triggering red alert.")
            blink_red_alert(wled)

    except Exception as e:
        logging.error(f"Error during blink sequence: {e}")
        # On exception => revert
        revert_to_user_default(wled)
    finally:
        # Always clear the flashing flag
        wled.flashing = False


# ======================
# Simulate Short Press
# ======================
def simulate_short_press(wled: 'WLEDController'):
    """
    Simulate a hardware short press from the web UI. Immediately stops any
    current flashing and then performs the blink_green_for_30s routine.
    """
    logging.info("Simulating short press from web UI.")
    wled.stop_flashing()
    blink_green_for_30s(wled)


# ======================
# Simulate Long Press
# ======================
def simulate_long_press(wled: 'WLEDController'):
    """
    Simulate a hardware long press from the web UI. Immediately stops any
    current flashing, then blinks red until the threshold is reached,
    after which we revert to the user default.
    """
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

            # If we've simulated holding long enough, end the blink
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
        # On exception => revert
        revert_to_user_default(wled)
    finally:
        # Always clear the flashing flag
        wled.flashing = False


# ======================
# Hardware Button Loop
# ======================
def hardware_button_loop(wled: 'WLEDController', stop_event: threading.Event):
    """
    Runs in a background thread, monitoring the physical hardware button for short and long presses.
    Blinks 'blue' for short presses, 'red' for long presses, reverting to user default when done.

    Args:
        wled (WLEDController): WLED controller instance.
        stop_event (threading.Event): Event that signals this loop should stop.
    """
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(Config.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Apply initial mode (user default) on startup
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

        # If the button is not pressed yet, check if it just got pressed:
        if not pressed:
            if current_state == 0:
                pressed = True
                press_start_time = time.time()
                blinking_red = False
                wled.stop_flashing()
        else:
            # If the button was pressed, check if it's been released
            if current_state == 1:
                duration = time.time() - press_start_time
                pressed = False

                # If we were already blinking red, that means a long press was in progress
                if blinking_red:
                    logging.info("Long press released => revert to default")
                    revert_to_user_default(wled)
                    blinking_red = False
                else:
                    # Check if it was short or long
                    threshold = Config.LONG_PRESS_THRESHOLD
                    if duration < threshold:
                        # It's a short press => do short press logic
                        blink_green_for_30s(wled)
                    else:
                        # It's a long press => blink red now
                        logging.info("Long press ended without in-press blinking => blink red now.")
                        blink_red_alert(wled)
            else:
                # The button is still being held
                held_duration = time.time() - press_start_time
                threshold = Config.LONG_PRESS_THRESHOLD

                # If we've hit the threshold and haven't started blinking red yet, start it
                if (held_duration >= threshold) and not blinking_red:
                    logging.info("Long press threshold reached => blinking red while held down")
                    blinking_red = True
                    blink_state = False
                    last_blink_time = time.time()

                # If we are in a long-press blink, keep toggling red/off
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
    Flask route decorator that limits each client IP to Config.API_RATE_LIMIT
    requests per minute. Returns 429 if exceeded.
    """
    requests_per_ip = {}

    @wraps(f)
    def decorated(*args, **kwargs):
        now = time.time()
        ip = request.remote_addr

        # Clean out old requests older than 60 seconds
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


@app.route("/")
@rate_limit
def index():
    """
    Renders the main page with current mode/effect information, configuration,
    and system health data. Also lists available WLED effects.
    """
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
    Updates WLED configuration settings from a form post.
    Includes effect speed/intensity, IP address, brightness, etc.
    Then writes changes to the INI file and applies the new default mode/effect.
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
    """
    Simulates a button press (short or long) from the web UI.
    Immediately calls the corresponding blink function.
    """
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
    """
    Returns JSON of the current system health (status, last error, etc.).
    """
    return jsonify(wled.get_health_status())


def background_connect_wled(wled: 'WLEDController', stop_event: threading.Event):
    """
    Background thread function to keep trying to connect/re-connect to WLED
    if disconnected. Runs until stop_event is set.
    """
    try:
        while not stop_event.is_set():
            if not wled.is_connected:
                wled.wait_for_connection()
            time.sleep(Config.HEALTH_CHECK_INTERVAL)
    except Exception as e:
        logging.error(f"Error in background_connect_wled: {e}")


def main():
    """
    Main entry point for the WLED button Flask application.
    1) Load config and validate.
    2) Set up logging.
    3) Initialize WLED Controller.
    4) Start background threads for WLED connection and hardware button loop.
    5) Start Flask app.
    """
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

        # Apply initial mode once at startup
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
