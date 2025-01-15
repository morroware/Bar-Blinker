#!/usr/bin/env python3

import configparser
import os
import ipaddress
import time
import random
import logging
import logging.handlers
import threading
from threading import Lock
import RPi.GPIO as GPIO
import requests
from requests.auth import HTTPBasicAuth
from flask import Flask, request, render_template, redirect, url_for

# ======================
# Configuration Class
# ======================
class Config:
    BUTTON_PIN = 18
    WLED_IP = "192.168.6.12"
    LONG_PRESS_THRESHOLD = 6.0  # Seconds to consider a press as long
    SHORT_FLASH_DURATION = 30.0  # Duration for green flashing
    FLASH_INTERVAL = 0.5  # Interval between flashes in seconds
    FLASH_BRIGHTNESS = 255
    LOG_FILE = os.path.expanduser("/home/tech/wled_button.log")
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    RECONNECT_DELAY = 5
    TRANSITION_TIME = 0.0
    REQUEST_TIMEOUT = 5
    INI_FILE_PATH = "blinker-configs.ini"

    # New Configuration Parameters
    DEFAULT_MODE = "white"  # Options: "white", "effect"
    DEFAULT_EFFECT_INDEX = 0  # Integer index of the effect
    WLED_USERNAME = None  # Add your username if authentication is enabled
    WLED_PASSWORD = None  # Add your password if authentication is enabled

    @classmethod
    def load_from_ini(cls, ini_path=None):
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

        cls.BUTTON_PIN = get_int("BUTTON_PIN", cls.BUTTON_PIN)
        cls.WLED_IP = get_str("WLED_IP", cls.WLED_IP)
        cls.LONG_PRESS_THRESHOLD = get_float("LONG_PRESS_THRESHOLD", cls.LONG_PRESS_THRESHOLD)
        cls.SHORT_FLASH_DURATION = get_float("SHORT_FLASH_DURATION", cls.SHORT_FLASH_DURATION)
        cls.FLASH_INTERVAL = get_float("FLASH_INTERVAL", cls.FLASH_INTERVAL)
        cls.FLASH_BRIGHTNESS = get_int("FLASH_BRIGHTNESS", cls.FLASH_BRIGHTNESS)
        cls.LOG_FILE = get_str("LOG_FILE", cls.LOG_FILE)
        cls.MAX_RETRIES = get_int("MAX_RETRIES", cls.MAX_RETRIES)
        cls.RETRY_DELAY = get_float("RETRY_DELAY", cls.RETRY_DELAY)
        cls.RECONNECT_DELAY = get_float("RECONNECT_DELAY", cls.RECONNECT_DELAY)
        cls.TRANSITION_TIME = get_float("TRANSITION_TIME", cls.TRANSITION_TIME)
        cls.REQUEST_TIMEOUT = get_float("REQUEST_TIMEOUT", cls.REQUEST_TIMEOUT)
        cls.DEFAULT_MODE = get_mode("DEFAULT_MODE", cls.DEFAULT_MODE)
        cls.DEFAULT_EFFECT_INDEX = get_int("DEFAULT_EFFECT_INDEX", cls.DEFAULT_EFFECT_INDEX)
        cls.WLED_USERNAME = parser.get(section, "WLED_USERNAME", fallback=None)
        cls.WLED_PASSWORD = parser.get(section, "WLED_PASSWORD", fallback=None)

    @classmethod
    def write_to_ini(cls):
        parser = configparser.ConfigParser()
        section = "BLINKER"
        parser.add_section(section)

        def set_str(key, value):
            parser.set(section, key, str(value))

        set_str("BUTTON_PIN", cls.BUTTON_PIN)
        set_str("WLED_IP", cls.WLED_IP)
        set_str("LONG_PRESS_THRESHOLD", cls.LONG_PRESS_THRESHOLD)
        set_str("SHORT_FLASH_DURATION", cls.SHORT_FLASH_DURATION)
        set_str("FLASH_INTERVAL", cls.FLASH_INTERVAL)
        set_str("FLASH_BRIGHTNESS", cls.FLASH_BRIGHTNESS)
        set_str("LOG_FILE", cls.LOG_FILE)
        set_str("MAX_RETRIES", cls.MAX_RETRIES)
        set_str("RETRY_DELAY", cls.RETRY_DELAY)
        set_str("RECONNECT_DELAY", cls.RECONNECT_DELAY)
        set_str("TRANSITION_TIME", cls.TRANSITION_TIME)
        set_str("REQUEST_TIMEOUT", cls.REQUEST_TIMEOUT)
        set_str("DEFAULT_MODE", cls.DEFAULT_MODE)
        set_str("DEFAULT_EFFECT_INDEX", cls.DEFAULT_EFFECT_INDEX)
        set_str("WLED_USERNAME", cls.WLED_USERNAME if cls.WLED_USERNAME else "")
        set_str("WLED_PASSWORD", cls.WLED_PASSWORD if cls.WLED_PASSWORD else "")

        with open(cls.INI_FILE_PATH, "w") as config_file:
            parser.write(config_file)

    @classmethod
    def validate(cls):
        try:
            ipaddress.ip_address(cls.WLED_IP)
            assert 0 <= cls.FLASH_BRIGHTNESS <= 255
            assert cls.SHORT_FLASH_DURATION > 0
            assert cls.FLASH_INTERVAL > 0
            assert cls.LONG_PRESS_THRESHOLD > 0
            assert 0 <= cls.BUTTON_PIN <= 27
            assert cls.DEFAULT_MODE in ["white", "effect"]
            assert 0 <= cls.DEFAULT_EFFECT_INDEX <= 200  # Assuming WLED supports a reasonable number of effects
            return True
        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False

# ======================
# Logging Setup Function
# ======================
def setup_logging():
    try:
        log_dir = os.path.dirname(Config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        handler = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE,
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

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger
    except Exception as e:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.error(f"Logging setup failed: {e}")
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
            # WLED API returns LED count directly in the info response
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True
            logging.info(f"Connected to {self.name} with {self.led_count} LEDs")
            return True
        self.is_connected = False
        return False

    def get_info(self):
        try:
            url = f"http://{self.ip_address}/json/info"
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            logging.error(f"Failed to get WLED info: HTTP {response.status_code}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED info: {e}")
            return None

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
                    return True
                logging.warning(f"Failed to set WLED state (Attempt {attempt+1}): HTTP {resp.status_code}")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Request error: {e}")
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
        """
        Sets the LEDs to white.
        """
        logging.info("Setting LEDs to white.")
        return self.set_color(255, 255, 255, Config.FLASH_BRIGHTNESS)

    def get_effects(self):
        """
        Retrieves the list of available effects from WLED.
        Returns a list of effect names.
        """
        try:
            url = f"http://{self.ip_address}/json"
            logging.debug(f"Fetching effects from {url}")
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)
            logging.debug(f"Received response: {response.status_code} - {response.text}")

            if response.status_code == 200:
                json_data = response.json()
                # Effects are in the 'effects' array of the main JSON response
                effects = json_data.get('effects', [])
                logging.info(f"Retrieved {len(effects)} effects from WLED")
                return effects
            else:
                logging.error(f"Failed to get WLED effects: HTTP {response.status_code}")
                return []
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED effects: {e}")
            return []
        except ValueError as e:
            logging.error(f"Invalid JSON response from WLED effects: {e}")
            return []

    def apply_effect(self, effect_index):
        """
        Applies an effect by its index from the fxList.
        """
        try:
            url = f"http://{self.ip_address}/json/state"
            payload = {
                "seg": [{
                    "fx": effect_index
                }]
            }
            logging.debug(f"Applying effect {effect_index} with payload: {payload}")
            response = self._session.post(url, json=payload, timeout=Config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                logging.info(f"Applied effect {effect_index}.")
                return True
            else:
                logging.error(f"Failed to apply effect {effect_index}: HTTP {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to apply effect {effect_index}: {e}")
            self.is_connected = False
            return False

    def cleanup(self):
        self.stop_flashing()
        self._session.close()

# =================================
# Helper: Revert to user-selected default
# =================================
def revert_to_user_default(wled: 'WLEDController'):
    """
    Reverts WLED to the user-selected default mode:
    either white or the chosen effect index.
    """
    logging.info("Reverting to user default...")
    if Config.DEFAULT_MODE == "white":
        wled.set_white()
    else:
        wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

# ======================
# Function to Blink Red Alert
# ======================
def blink_red_alert(wled: 'WLEDController'):
    """
    Function to handle red alert blinking after a long press was initiated but not completed.
    """
    logging.info("Issuing red alert due to incomplete long press.")
    start_time = time.time()
    flash_state = True
    wled.flashing = True

    try:
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            interval = Config.FLASH_INTERVAL / 2
            if flash_state:
                wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)
            else:
                wled.set_color(0, 0, 0, 0)
            flash_state = not flash_state
            time.sleep(interval)
        # Instead of forcing white, revert to default
        revert_to_user_default(wled)
    except Exception as e:
        logging.error(f"Error during red alert blinking: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Function to Blink Green for Short Press
# ======================
def blink_green_for_30s(wled: 'WLEDController'):
    """
    Blinks green LEDs for SHORT_FLASH_DURATION seconds.
    If a long press is detected during this period, switches to blinking red.
    """
    import RPi.GPIO as GPIO

    logging.info("Short press => blink 'green' for up to SHORT_FLASH_DURATION seconds")

    start_time = time.time()
    flash_state = True
    wled.flashing = True

    press_start_time = None
    long_press_active = False
    long_press_initiated = False  # Flag to track long press initiation

    try:
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            # Check for button press
            if GPIO.input(Config.BUTTON_PIN) == 0:
                if press_start_time is None:
                    press_start_time = time.time()
                elif (time.time() - press_start_time) >= Config.LONG_PRESS_THRESHOLD and not long_press_active:
                    logging.info("Long press detected during green => switching to red immediately")
                    long_press_active = True
                    long_press_initiated = True  # Set the flag
                    while GPIO.input(Config.BUTTON_PIN) == 0 and wled.flashing:
                        interval = Config.FLASH_INTERVAL / 2
                        if flash_state:
                            wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)
                        else:
                            wled.set_color(0, 0, 0, 0)
                        flash_state = not flash_state
                        time.sleep(interval)
                    # Revert to default
                    revert_to_user_default(wled)
                    return
            else:
                press_start_time = None

            # Flash green
            interval = Config.FLASH_INTERVAL / 2
            if flash_state:
                wled.set_color(0, 0, 255, Config.FLASH_BRIGHTNESS)
            else:
                wled.set_color(0, 0, 0, 0)
            flash_state = not flash_state
            time.sleep(interval)

        # After green flashing duration, revert to default
        revert_to_user_default(wled)

        if long_press_initiated:
            logging.info("Long press was initiated during green flashing but not completed. Triggering red alert.")
            blink_red_alert(wled)

    except Exception as e:
        logging.error(f"Error during blink sequence: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Function to Simulate Short Press via Web UI
# ======================
def simulate_short_press(wled: 'WLEDController'):
    """
    Simulates a short button press, triggering green flashing.
    """
    logging.info("Simulating short press from web UI.")
    wled.stop_flashing()
    blink_green_for_30s(wled)

# ======================
# Function to Simulate Long Press via Web UI
# ======================
def simulate_long_press(wled: 'WLEDController'):
    """
    Simulates a long button press, triggering red blinking.
    """
    logging.info("Simulating long press from web UI.")

    import RPi.GPIO as GPIO
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
                # Instead of going white, revert to default
                revert_to_user_default(wled)
                logging.info("Simulated long press release => reverting to default")
                break

            now = time.time()
            if (now - last_blink_time) >= interval:
                if blink_state:
                    wled.set_color(0, 0, 0, 0)
                else:
                    wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)
                blink_state = not blink_state
                last_blink_time = now

            time.sleep(0.01)
    except Exception as e:
        logging.error(f"Error during long press simulation: {e}")
        wled.restore_last_state()
    finally:
        wled.flashing = False

# ======================
# Hardware Button Loop Function
# ======================
def hardware_button_loop(wled: 'WLEDController', stop_event: threading.Event):
    """
    Monitors the hardware button for short and long presses.
    """
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
            wled.wait_for_connection()
            wled.restore_last_state()

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
                            wled.set_color(0, 0, 0, 0)
                        else:
                            wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)
                        blink_state = not blink_state
                        last_blink_time = now

        time.sleep(0.01)

    GPIO.cleanup()
    logging.info("Hardware button loop exiting...")

# ======================
# Flask Web Application Setup
# ======================
app = Flask(__name__)
stop_event = threading.Event()
wled = None  # Will be initialized in main()

@app.route("/")
def index():
    if not wled.is_connected:
        logging.warning("WLED not connected. Effects will not be available.")
        effects = []
    else:
        effects = wled.get_effects()
    current_effect = Config.DEFAULT_EFFECT_INDEX if Config.DEFAULT_MODE == "effect" else None
    current_mode = Config.DEFAULT_MODE
    logging.info(f"Rendering index.html with mode={current_mode}, effect_index={current_effect}, effects={effects}")
    return render_template("index.html",
                           c=Config,
                           effects=effects,
                           current_mode=current_mode,
                           current_effect=current_effect)

@app.route("/update_config", methods=["POST"])
def update_config():
    form = request.form

    # Update existing Config parameters
    Config.WLED_IP = form.get("WLED_IP", Config.WLED_IP)
    Config.LONG_PRESS_THRESHOLD = float(form.get("LONG_PRESS_THRESHOLD", Config.LONG_PRESS_THRESHOLD))
    Config.SHORT_FLASH_DURATION = float(form.get("SHORT_FLASH_DURATION", Config.SHORT_FLASH_DURATION))
    Config.FLASH_INTERVAL = float(form.get("FLASH_INTERVAL", Config.FLASH_INTERVAL))
    Config.FLASH_BRIGHTNESS = int(form.get("FLASH_BRIGHTNESS", Config.FLASH_BRIGHTNESS))
    Config.LOG_FILE = form.get("LOG_FILE", Config.LOG_FILE)
    Config.MAX_RETRIES = int(form.get("MAX_RETRIES", Config.MAX_RETRIES))
    Config.RETRY_DELAY = float(form.get("RETRY_DELAY", Config.RETRY_DELAY))
    Config.RECONNECT_DELAY = float(form.get("RECONNECT_DELAY", Config.RECONNECT_DELAY))
    Config.TRANSITION_TIME = float(form.get("TRANSITION_TIME", Config.TRANSITION_TIME))
    Config.REQUEST_TIMEOUT = float(form.get("REQUEST_TIMEOUT", Config.REQUEST_TIMEOUT))
    Config.WLED_USERNAME = form.get("WLED_USERNAME", Config.WLED_USERNAME)
    Config.WLED_PASSWORD = form.get("WLED_PASSWORD", Config.WLED_PASSWORD)

    # Update Mode and Effect Selection
    selected_mode = form.get("mode", Config.DEFAULT_MODE)
    if selected_mode not in ["white", "effect"]:
        logging.warning(f"Invalid mode selected: {selected_mode}. Reverting to default.")
        selected_mode = "white"
    Config.DEFAULT_MODE = selected_mode

    if selected_mode == "effect":
        try:
            effect_index = int(form.get("effect_index", Config.DEFAULT_EFFECT_INDEX))
            Config.DEFAULT_EFFECT_INDEX = effect_index
        except ValueError:
            logging.warning(f"Invalid effect index format. Reverting to default.")
            effect_index = Config.DEFAULT_EFFECT_INDEX
    else:
        effect_index = None  # No effect selected

    Config.write_to_ini()
    logging.info("Updated config from web UI. New settings apply immediately in blinking logic.")

    # Apply the selected mode immediately
    if selected_mode == "white":
        wled.set_white()
    elif selected_mode == "effect" and effect_index is not None:
        wled.apply_effect(effect_index)

    return redirect(url_for("index"))

@app.route("/simulate_press", methods=["POST"])
def simulate_press():
    press_type = request.form.get("press_type")
    if press_type == "short":
        simulate_short_press(wled)
    elif press_type == "long":
        simulate_long_press(wled)
    else:
        logging.warning(f"Unknown press type: {press_type}")
    return redirect(url_for("index"))

# ======================
# Background Connection Thread Function
# ======================
def background_connect_wled(wled: 'WLEDController', stop_event: threading.Event):
    """
    Continuously attempts to connect to WLED in the background.
    """
    try:
        while not wled.is_connected and not stop_event.is_set():
            wled.wait_for_connection()
    except Exception as e:
        logging.error(f"Error in background_connect_wled: {e}")

# ======================
# Main Function
# ======================
def main():
    Config.load_from_ini("blinker-configs.ini")
    setup_logging()
    if not Config.validate():
        logging.error("Invalid configuration; exiting.")
        return

    logging.info("Starting WLED Button Flask Application...")

    global wled
    wled = WLEDController(
        Config.WLED_IP,
        username=getattr(Config, 'WLED_USERNAME', None),
        password=getattr(Config, 'WLED_PASSWORD', None)
    )

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

    # Apply the initial mode based on configuration
    if Config.DEFAULT_MODE == "white":
        wled.set_white()
    elif Config.DEFAULT_MODE == "effect":
        wled.apply_effect(Config.DEFAULT_EFFECT_INDEX)

    # Start Flask app
    app.run(host="0.0.0.0", port=5000, debug=False)

    # Cleanup after Flask app stops
    stop_event.set()
    hardware_thread.join()
    connect_thread.join()
    wled.cleanup()

# ======================
# Entry Point
# ======================
if __name__ == "__main__":
    main()

