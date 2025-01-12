#!/usr/bin/env python3

"""
This script controls a WLED device using a Raspberry Pi push-button.
It uses a polling approach rather than GPIO event detection to avoid
phantom presses or spurious events.

Features:
1. A short press (< LONG_PRESS_THRESHOLD seconds) triggers a 30-second blink of "green."
2. A long press (>= LONG_PRESS_THRESHOLD seconds) starts blinking "red" while the button is still held down.
3. Once the user releases after a long press, the system goes back to white.
4. The script also includes logic to reconnect to WLED if the connection is lost.
"""

import RPi.GPIO as GPIO
import requests
import time
import random
import logging
import logging.handlers
import os
import ipaddress
from threading import Lock

class Config:
    """
    A configuration class holding various settings for the script.
    
    Attributes:
        BUTTON_PIN (int): The BCM pin number to which your button is connected.
        WLED_IP (str): The IP address of the WLED device on your network.
        LONG_PRESS_THRESHOLD (float): The number of seconds that defines a "long press."
        SHORT_FLASH_DURATION (float): The number of seconds to blink "green" for a short press.
        FLASH_INTERVAL (float): The delay (in seconds) between toggles (ON/OFF) in blinking sequences.
        FLASH_BRIGHTNESS (int): Brightness level (0-255) for blinking colors.
        LOG_FILE (str): The path where the log file will be stored.
        MAX_RETRIES (int): Number of times to retry if WLED state-setting fails.
        RETRY_DELAY (float): The base delay (in seconds) between retries for WLED requests.
        RECONNECT_DELAY (float): The base delay (in seconds) between reconnect attempts to WLED.
        TRANSITION_TIME (float): Transition time in seconds for WLED color changes.
        REQUEST_TIMEOUT (float): HTTP request timeout in seconds.
    """
    BUTTON_PIN = 18
    WLED_IP = "192.168.6.12"

    # Time thresholds
    LONG_PRESS_THRESHOLD = 6.0      # If button is held >= 6s, we consider it a long press
    SHORT_FLASH_DURATION = 30.0     # For short press, blink "green" for 30 seconds
    FLASH_INTERVAL = 0.5            # The half-period for blinking (on/off)
    FLASH_BRIGHTNESS = 255          # Brightness level for blinking

    LOG_FILE = os.path.expanduser("~/wled_button.log")
    MAX_RETRIES = 3
    RETRY_DELAY = 1
    RECONNECT_DELAY = 5
    TRANSITION_TIME = 0.0
    REQUEST_TIMEOUT = 5

    @classmethod
    def validate(cls):
        """
        Validates the configuration settings to ensure they are within safe ranges
        and that the IP address is valid.

        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        try:
            # Validate the IP address by attempting to parse it
            ipaddress.ip_address(cls.WLED_IP)
            
            # Validate numeric ranges
            assert 0 <= cls.FLASH_BRIGHTNESS <= 255
            assert cls.SHORT_FLASH_DURATION > 0
            assert cls.FLASH_INTERVAL > 0
            assert cls.LONG_PRESS_THRESHOLD > 0
            
            # Validate GPIO pin range (BCM mode)
            assert 0 <= cls.BUTTON_PIN <= 27
            
            return True
        except Exception as e:
            logging.error(f"Configuration validation failed: {e}")
            return False

def setup_logging():
    """
    Configures a rotating file handler and a console handler for logging.
    If the log directory doesn't exist, it creates one.

    Returns:
        logging.Logger: The configured logger instance.
    """
    try:
        # Determine the directory part of the log file path
        log_dir = os.path.dirname(Config.LOG_FILE)
        # Create the directory if it doesn't exist
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Create a rotating file handler that will automatically rotate when size exceeds 1 MB
        handler = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=1024 * 1024,  # 1 MB
            backupCount=5
        )
        # Create a formatter: how each log message will be formatted
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Create the root logger and attach the rotating file handler
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        
        # Also create a console handler so logs appear in the terminal too
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        return logger
    except Exception as e:
        # If setting up a file-based logger fails, fallback to a simple console-only logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.error(f"Logging setup failed: {e}")
        return logging.getLogger()

class WLEDController:
    """
    Manages communication with a WLED device over HTTP endpoints.

    Attributes:
        ip_address (str): The IP address of the WLED device.
        led_count (int): Number of LEDs in the WLED device.
        name (str): Name of the WLED device.
        version (str): Firmware version of the WLED device.
        is_connected (bool): Whether the device is successfully connected.
        _last_state (dict): The last state (JSON) sent to WLED.
        _state_lock (threading.Lock): Ensures thread-safe updates to _last_state.
        _flash_lock (threading.Lock): Ensures thread-safe updates to _flashing.
        _flashing (bool): Indicates whether a flash sequence is ongoing.
        _session (requests.Session): Reusable session for HTTP requests.
    """
    def __init__(self, ip_address):
        """
        Initializes the WLEDController with the device IP and default states.

        Args:
            ip_address (str): The IP address of the WLED device.
        """
        self.ip_address = ip_address
        self.led_count = 0
        self.name = "Unknown"
        self.version = "Unknown"
        self.is_connected = False
        self._last_state = None
        self._state_lock = Lock()
        self._flash_lock = Lock()
        self._flashing = False
        self._session = requests.Session()
        
    @property
    def flashing(self):
        """
        Thread-safe getter for the flashing state.
        Returns:
            bool: True if a flash sequence is currently active, False otherwise.
        """
        with self._flash_lock:
            return self._flashing
            
    @flashing.setter
    def flashing(self, value):
        """
        Thread-safe setter for the flashing state.
        """
        with self._flash_lock:
            self._flashing = value

    def initialize(self):
        """
        Fetch device info from the WLED /json/info endpoint.
        If successful, populates attributes like led_count, name, version,
        and sets is_connected to True.

        Returns:
            bool: True if the device is successfully contacted, False otherwise.
        """
        info = self.get_info()
        if info:
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True
            logging.info(f"Connected to {self.name} with {self.led_count} LEDs")
            return True
        self.is_connected = False
        return False

    def get_info(self):
        """
        Sends an HTTP GET request to /json/info on the WLED device.

        Returns:
            dict or None: The WLED JSON info if successful, or None on failure.
        """
        try:
            url = f"http://{self.ip_address}/json/info"
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            logging.error(f"Failed to get WLED info: Status {response.status_code}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED info: {e}")
            return None

    def wait_for_connection(self):
        """
        Attempts to connect (call initialize()) with exponential backoff.
        Retries until successful. If the device can't be contacted,
        this method will keep looping until it can.

        Returns:
            bool: True once connected.
        """
        attempt = 1
        max_delay = 60
        while not self.is_connected:
            logging.info(f"Connection attempt {attempt}...")
            if self.initialize():
                return True
            # Exponential backoff with jitter
            delay = min(Config.RECONNECT_DELAY * (2 ** (attempt - 1)), max_delay)
            jitter = delay * 0.1
            adjusted_delay = delay + (random.random() * jitter)
            attempt += 1
            time.sleep(adjusted_delay)
        return True

    def set_color(self, red, green, blue, brightness=255):
        """
        Sends a command to WLED to set the entire strip to a single color
        and brightness.

        Args:
            red (int): Red component (0-255).
            green (int): Green component (0-255).
            blue (int): Blue component (0-255).
            brightness (int): Overall brightness (0-255).

        Returns:
            bool: True if the command succeeds, False otherwise.
        """
        if not self.is_connected or self.led_count == 0:
            return False

        state = {
            "on": True,
            "bri": brightness,
            "transition": int(Config.TRANSITION_TIME * 1000),
            "seg": [{
                "id": 0,
                "col": [[red, green, blue]],
                "fx": 0,  # solid effect
                "sx": 0,  # speed
                "ix": 0   # intensity
            }]
        }
        return self._send_state(state)

    def _send_state(self, state):
        """
        Sends a POST to /json/state with the provided JSON 'state'.
        Implements simple retry logic if the request fails.

        Args:
            state (dict): The desired WLED state.

        Returns:
            bool: True if successful, False otherwise.
        """
        url = f"http://{self.ip_address}/json/state"
        for attempt in range(Config.MAX_RETRIES):
            try:
                response = self._session.post(url, json=state, timeout=Config.REQUEST_TIMEOUT)
                if response.status_code == 200:
                    with self._state_lock:
                        self._last_state = state
                    return True
                logging.warning(f"Failed to set state (Attempt {attempt+1}): Status {response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Request error: {e}")
                self.is_connected = False

            if attempt < Config.MAX_RETRIES - 1:
                time.sleep(Config.RETRY_DELAY * (2 ** attempt))
        return False

    def stop_flashing(self):
        """
        Sets the internal flashing flag to False, which can be used
        to end a blink loop.
        """
        self.flashing = False

    def restore_last_state(self):
        """
        Re-applies the last known state (if any) to WLED. If _last_state is None,
        does nothing.

        Returns:
            bool: True if successfully restored last state, False otherwise.
        """
        with self._state_lock:
            if self._last_state:
                logging.info("Restoring last known WLED state")
                return self._send_state(self._last_state)
        return False

    def cleanup(self):
        """
        Called at script shutdown to stop any flashing and close the session.
        """
        self.stop_flashing()
        self._session.close()

def blink_green_for_30s(wled: WLEDController):
    """
    Blinks "green" for 30 seconds as a response to a short press.
    This function is blocking, meaning no new presses are processed
    while it's running.

    Args:
        wled (WLEDController): The WLED controller instance to send commands to.
    """
    logging.info("Short press => blink 'green' 30s")
    start_time = time.time()
    flash_state = True
    wled.flashing = True  # Mark that a flash/bink is active

    try:
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            if flash_state:
                # Adjust to your hardware’s “green”: e.g., (0,255,0) or (0,0,255).
                # We'll assume (0,0,255) is "green" as per your original script.
                wled.set_color(0, 0, 255, Config.FLASH_BRIGHTNESS)
            else:
                wled.set_color(0, 0, 0, 0)
            flash_state = not flash_state
            # Wait half the FLASH_INTERVAL, so effectively a full on/off cycle is FLASH_INTERVAL seconds
            time.sleep(Config.FLASH_INTERVAL / 2)

        # After blinking ends, set the strip to white
        wled.set_color(255, 255, 255)

    except Exception as e:
        logging.error(f"Short press blink error: {e}")
        # If something goes wrong, try to restore last known WLED state
        wled.restore_last_state()
    finally:
        # Whether successful or errored, mark flashing as done
        wled.flashing = False

def main():
    """
    The main function sets up logging, checks configuration, and runs
    a polling loop to watch the button state:
      - If the button is pressed for under LONG_PRESS_THRESHOLD seconds,
        we treat it as a short press, blinking green for 30s.
      - If the user keeps holding it beyond LONG_PRESS_THRESHOLD seconds,
        we blink red until the user releases. Once released, we return to white.
    """
    # Validate config
    if not Config.validate():
        logging.error("Invalid configuration")
        return

    # Prepare logging
    setup_logging()
    logging.info("WLED Button Control Starting...")

    # Create our WLED controller and attempt to connect
    wled = WLEDController(Config.WLED_IP)
    wled.wait_for_connection()

    # Configure GPIO
    GPIO.setmode(GPIO.BCM)
    # Use an internal pull-up so the button pin reads 1 normally,
    # and 0 when pressed (assuming a momentary button to ground).
    GPIO.setup(Config.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # Start the LED strip in white
    wled.set_color(255, 255, 255)

    # Variables to track button press logic
    pressed = False          # Whether the button is currently pressed
    press_start_time = 0.0   # When we started pressing
    blinking_red = False     # True once we cross the LONG_PRESS_THRESHOLD
    blink_state = False      # Used to track toggling "red" on/off
    last_blink_time = 0.0    # Timestamp of the last red toggle
    blink_interval = Config.FLASH_INTERVAL / 2.0  # We blink on/off every half-interval

    try:
        # Main loop: polls the button state 100 times/second (sleep 0.01)
        while True:
            # 1. Check if we are still connected to WLED; if not, attempt reconnect
            if not wled.is_connected:
                logging.warning("Lost connection to WLED")
                wled.wait_for_connection()
                wled.restore_last_state()

            # 2. Read the button (0 = pressed, 1 = not pressed)
            current_state = GPIO.input(Config.BUTTON_PIN)

            # 3. Logic for pressed/unpressed states
            if not pressed:
                # If previously not pressed...
                if current_state == 0:
                    # The button is now pressed!
                    pressed = True
                    press_start_time = time.time()
                    blinking_red = False
                    # Stop any green flashing if it was ongoing
                    wled.stop_flashing()
                    # We remain in white until we decide short/long press
            else:
                # If previously pressed...
                if current_state == 1:
                    # The button is now released
                    press_duration = time.time() - press_start_time
                    pressed = False

                    if blinking_red:
                        # If we were blinking red in real-time (long press),
                        # user has just released => stop blinking and go white.
                        logging.info("Long press released => restore white")
                        wled.set_color(255, 255, 255)
                        blinking_red = False
                    else:
                        # If not blinking red, then the press was < LONG_PRESS_THRESHOLD
                        if press_duration < Config.LONG_PRESS_THRESHOLD:
                            # => short press => blink green for 30 seconds
                            blink_green_for_30s(wled)
                        else:
                            # Edge case: pressed longer than threshold
                            # but never started blinking in-press for some reason.
                            # We can blink red here if you want a post-release action:
                            logging.info("Long press ended without in-press blinking => blink red now.")
                            start = time.time()
                            flash_state = True
                            wled.flashing = True
                            while (time.time() - start < Config.SHORT_FLASH_DURATION) and wled.flashing:
                                if flash_state:
                                    # Based on your hardware, "red" might be (0,255,0):
                                    wled.set_color(0, 255, 0, Config.FLASH_BRIGHTNESS)
                                else:
                                    wled.set_color(0, 0, 0, 0)
                                flash_state = not flash_state
                                time.sleep(Config.FLASH_INTERVAL / 2)
                            # After blinking, go white
                            wled.set_color(255, 255, 255)
                            wled.flashing = False

                else:
                    # The button is still being held down
                    held_duration = time.time() - press_start_time
                    # If we've crossed the threshold and not yet started blinking red...
                    if (held_duration >= Config.LONG_PRESS_THRESHOLD) and not blinking_red:
                        # Start blinking red while the user is still holding
                        logging.info("Long press threshold reached => blinking red while held down")
                        blinking_red = True
                        blink_state = False
                        last_blink_time = time.time()

                    # If currently blinking red, toggle at intervals
                    if blinking_red:
                        now = time.time()
                        if now - last_blink_time >= blink_interval:
                            if blink_state:
                                # Turn off
                                wled.set_color(0, 0, 0, 0)
                            else:
                                # "Red" on your hardware might be (0,255,0).
                                wled.set_color(0, 255, 0, Config.FLASH_BRIGHTNESS)
                            blink_state = not blink_state
                            last_blink_time = now

            # Polling rate: 10 ms
            time.sleep(0.01)

    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
    finally:
        # Clean up
        wled.cleanup()
        GPIO.cleanup()

if __name__ == "__main__":
    main()
