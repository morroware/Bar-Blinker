#!/usr/bin/env python3
"""
This is a Python script designed to control WLED (a popular LED controller) using a physical button connected to a Raspberry Pi.
It also provides a web interface using Flask to update configurations and simulate button presses.
The script handles different types of button presses (short and long) to perform actions like blinking LEDs in specific colors.
Logging is implemented to track the application's behavior and issues.
"""

# Importing necessary libraries and modules
import configparser       # For handling configuration files
import os                 # For interacting with the operating system (e.g., file paths)
import ipaddress          # For validating and handling IP addresses
import time               # For time-related functions (e.g., sleep, timestamps)
import random             # For generating random numbers (used for jitter in reconnection attempts)
import logging            # For logging events, errors, and informational messages
import logging.handlers   # For advanced logging features like rotating file handlers
import threading          # For handling multiple threads of execution
from threading import Lock # For ensuring thread-safe operations
import RPi.GPIO as GPIO    # For interacting with the Raspberry Pi's GPIO pins
import requests           # For making HTTP requests to the WLED device
from flask import Flask, request, render_template, redirect, url_for # For creating a web server and handling web requests

# Define a configuration class to manage application settings
class Config:
    """
    The Config class holds all the configuration parameters for the application.
    It can load these parameters from an INI file and validate them.
    """
    # Default configuration values
    BUTTON_PIN = 18  # GPIO pin number where the button is connected
    WLED_IP = "192.168.6.12"  # IP address of the WLED device
    LONG_PRESS_THRESHOLD = 6.0  # Time in seconds to consider a button press as a long press
    SHORT_FLASH_DURATION = 30.0  # Duration in seconds for which the LEDs will flash on a short press
    FLASH_INTERVAL = 0.5  # Time interval in seconds between LED flashes
    FLASH_BRIGHTNESS = 255  # Brightness level of the LEDs (0-255)
    LOG_FILE = os.path.expanduser("~/wled_button.log")  # Path to the log file
    MAX_RETRIES = 3  # Maximum number of retries for HTTP requests
    RETRY_DELAY = 1  # Delay in seconds between retry attempts
    RECONNECT_DELAY = 5  # Initial delay in seconds before attempting to reconnect to WLED
    TRANSITION_TIME = 0.0  # Transition time for LED color changes in seconds
    REQUEST_TIMEOUT = 5  # Timeout in seconds for HTTP requests
    INI_FILE_PATH = "blinker-configs.ini"  # Path to the configuration INI file

    @classmethod
    def load_from_ini(cls, ini_path=None):
        """
        Load configuration parameters from an INI file.
        If no path is provided, it uses the default INI_FILE_PATH.
        """
        if ini_path:
            cls.INI_FILE_PATH = ini_path  # Update the INI file path if provided

        # Create a ConfigParser object to read the INI file
        parser = configparser.ConfigParser()
        read_files = parser.read(cls.INI_FILE_PATH)  # Attempt to read the INI file

        # If the INI file could not be read, log a warning and use default values
        if not read_files:
            logging.warning(f"Could not read config file: {cls.INI_FILE_PATH}. Using defaults.")

        section = "BLINKER"  # Define the section in the INI file where configurations are stored

        # Helper function to get string values from the INI file
        def get_str(key, default):
            return parser.get(section, key, fallback=str(default))

        # Helper function to get integer values from the INI file with error handling
        def get_int(key, default):
            val_str = parser.get(section, key, fallback=str(default))
            try:
                return int(val_str)
            except ValueError:
                logging.warning(f"Invalid int for {key}: {val_str}. Using default={default}.")
                return default

        # Helper function to get float values from the INI file with error handling
        def get_float(key, default):
            val_str = parser.get(section, key, fallback=str(default))
            try:
                return float(val_str)
            except ValueError:
                logging.warning(f"Invalid float for {key}: {val_str}. Using default={default}.")
                return default

        # Load each configuration parameter using the helper functions
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

    @classmethod
    def write_to_ini(cls):
        """
        Write the current configuration parameters to the INI file.
        """
        parser = configparser.ConfigParser()  # Create a new ConfigParser object
        section = "BLINKER"  # Define the section name
        parser.add_section(section)  # Add the section to the INI file

        # Helper function to set string values in the INI file
        def set_str(key, value):
            parser.set(section, key, str(value))

        # Set each configuration parameter in the INI file
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

        # Open the INI file in write mode and save the configurations
        with open(cls.INI_FILE_PATH, "w") as config_file:
            parser.write(config_file)

    @classmethod
    def validate(cls):
        """
        Validate the configuration parameters to ensure they are within acceptable ranges.
        Returns True if all validations pass, otherwise False.
        """
        try:
            # Validate that WLED_IP is a valid IP address
            ipaddress.ip_address(cls.WLED_IP)
            # Ensure FLASH_BRIGHTNESS is between 0 and 255
            assert 0 <= cls.FLASH_BRIGHTNESS <= 255
            # Ensure durations and intervals are positive
            assert cls.SHORT_FLASH_DURATION > 0
            assert cls.FLASH_INTERVAL > 0
            assert cls.LONG_PRESS_THRESHOLD > 0
            # Validate that BUTTON_PIN is within valid GPIO pin range (0-27 for Raspberry Pi)
            assert 0 <= cls.BUTTON_PIN <= 27
            return True  # All validations passed
        except Exception as e:
            # Log an error if any validation fails
            logging.error(f"Configuration validation failed: {e}")
            return False

def setup_logging():
    """
    Set up the logging configuration to log messages to both a file and the console.
    Uses a rotating file handler to prevent log files from becoming too large.
    Returns the configured logger.
    """
    try:
        # Determine the directory where the log file will be stored
        log_dir = os.path.dirname(Config.LOG_FILE)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)  # Create the directory if it doesn't exist

        # Create a rotating file handler that logs to the specified log file
        handler = logging.handlers.RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=1024 * 1024,  # Maximum size of a log file before it's rotated (1MB)
            backupCount=5           # Number of backup log files to keep
        )
        # Define the format of the log messages
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'  # Date and time format
        )
        handler.setFormatter(formatter)  # Set the formatter for the file handler

        logger = logging.getLogger()  # Get the root logger
        logger.addHandler(handler)     # Add the file handler to the logger
        logger.setLevel(logging.INFO)  # Set the logging level to INFO

        # Also log messages to the console
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        return logger  # Return the configured logger
    except Exception as e:
        # If setting up logging fails, fall back to basic configuration
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.error(f"Logging setup failed: {e}")
        return logging.getLogger()

class WLEDController:
    """
    The WLEDController class manages communication with a WLED device.
    It handles connecting to the device, sending color changes, and managing the device's state.
    """
    def __init__(self, ip_address):
        """
        Initialize the WLEDController with the given IP address.
        """
        self.ip_address = ip_address  # IP address of the WLED device
        self.led_count = 0            # Number of LEDs connected to the WLED device
        self.name = "Unknown"         # Name of the WLED device
        self.version = "Unknown"      # Firmware version of the WLED device
        self.is_connected = False     # Connection status to the WLED device
        self._last_state = None       # Last known state of the WLED device
        self._state_lock = Lock()     # Lock to ensure thread-safe access to _last_state
        self._flash_lock = Lock()     # Lock to ensure thread-safe access to flashing state
        self._flashing = False        # Indicates whether the LEDs are currently flashing
        self._session = requests.Session()  # Session object for making HTTP requests

    @property
    def flashing(self):
        """
        Property to get the current flashing state in a thread-safe manner.
        """
        with self._flash_lock:
            return self._flashing

    @flashing.setter
    def flashing(self, value):
        """
        Property setter to update the flashing state in a thread-safe manner.
        """
        with self._flash_lock:
            self._flashing = value

    def initialize(self):
        """
        Initialize the connection to the WLED device by fetching its information.
        Sets the LED count, name, and version if successful.
        Returns True if initialization is successful, otherwise False.
        """
        info = self.get_info()  # Fetch information from the WLED device
        if info:
            # Extract LED count, name, and version from the retrieved information
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True  # Update connection status
            logging.info(f"Connected to {self.name} with {self.led_count} LEDs")
            return True
        self.is_connected = False  # Update connection status if initialization failed
        return False

    def get_info(self):
        """
        Retrieve information from the WLED device by making an HTTP GET request.
        Returns the JSON response as a dictionary if successful, otherwise None.
        """
        try:
            url = f"http://{self.ip_address}/json/info"  # URL to fetch WLED info
            response = self._session.get(url, timeout=Config.REQUEST_TIMEOUT)  # Make the HTTP GET request
            if response.status_code == 200:
                return response.json()  # Return the JSON response if the request was successful
            logging.error(f"Failed to get WLED info: HTTP {response.status_code}")
            return None
        except requests.exceptions.RequestException as e:
            # Log any exceptions that occur during the HTTP request
            logging.error(f"Failed to get WLED info: {e}")
            return None

    def wait_for_connection(self):
        """
        Continuously attempt to connect to the WLED device until successful.
        Implements exponential backoff with jitter to handle reconnection attempts.
        Returns True once connected.
        """
        attempt = 1          # Initialize the attempt counter
        max_delay = 60       # Maximum delay between reconnection attempts (in seconds)
        while not self.is_connected:
            logging.info(f"Connection attempt {attempt}...")
            if self.initialize():
                return True  # Exit the loop if initialization is successful
            # Calculate the delay using exponential backoff
            delay = min(Config.RECONNECT_DELAY * (2 ** (attempt - 1)), max_delay)
            jitter = delay * 0.1  # Add a small random jitter to the delay
            time.sleep(delay + (random.random() * jitter))  # Wait before the next attempt
            attempt += 1
        return True

    def set_color(self, r, g, b, brightness=255):
        """
        Set the color of the LEDs by sending a state update to the WLED device.
        Parameters:
            r (int): Red component (0-255)
            g (int): Green component (0-255)
            b (int): Blue component (0-255)
            brightness (int): Brightness level (0-255)
        Returns True if the color was set successfully, otherwise False.
        """
        if not self.is_connected or self.led_count == 0:
            return False  # Cannot set color if not connected or no LEDs are present
        # Define the desired state for the LEDs
        state = {
            "on": True,  # Turn the LEDs on
            "bri": brightness,  # Set brightness
            "transition": int(Config.TRANSITION_TIME * 1000),  # Transition time in milliseconds
            "seg": [{
                "id": 0,
                "col": [[r, g, b]],  # Set the color for the segment
                "fx": 0,              # No special effects
                "sx": 0,              # Speed parameter (unused)
                "ix": 0               # Intensity parameter (unused)
            }]
        }
        return self._send_state(state)  # Send the state to the WLED device

    def _send_state(self, state):
        """
        Send a state update to the WLED device via an HTTP POST request.
        Implements retry logic in case of failures.
        Parameters:
            state (dict): The state to send to the WLED device
        Returns True if the state was sent successfully, otherwise False.
        """
        url = f"http://{self.ip_address}/json/state"  # URL to send the state update
        for attempt in range(Config.MAX_RETRIES):
            try:
                # Make the HTTP POST request with the state as JSON
                resp = self._session.post(url, json=state, timeout=Config.REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    with self._state_lock:
                        self._last_state = state  # Save the last known state
                    return True  # State update was successful
                logging.warning(f"Failed to set WLED state (Attempt {attempt+1}): HTTP {resp.status_code}")
            except requests.exceptions.RequestException as e:
                # Log any exceptions that occur during the HTTP request
                logging.warning(f"Request error: {e}")
                self.is_connected = False  # Update connection status

            if attempt < Config.MAX_RETRIES - 1:
                # Calculate delay before the next retry using exponential backoff
                time.sleep(Config.RETRY_DELAY * (2 ** attempt))
        return False  # All retry attempts failed

    def stop_flashing(self):
        """
        Stop any ongoing flashing by setting the flashing flag to False.
        """
        self.flashing = False

    def restore_last_state(self):
        """
        Restore the last known state of the WLED device.
        Returns True if the state was restored successfully, otherwise False.
        """
        with self._state_lock:
            if self._last_state:
                logging.info("Restoring last known WLED state")
                return self._send_state(self._last_state)
        return False

    def cleanup(self):
        """
        Perform cleanup operations when shutting down.
        Stops flashing and closes the HTTP session.
        """
        self.stop_flashing()
        self._session.close()

def blink_green_for_30s(wled: WLEDController):
    """
    Blink the LEDs green for a short press. This function runs for up to SHORT_FLASH_DURATION seconds.
    It also monitors for a long press during the blinking sequence to switch to red immediately.
    Parameters:
        wled (WLEDController): The WLEDController instance to control the LEDs
    """
    import RPi.GPIO as GPIO  # Import GPIO here to avoid circular imports

    logging.info("Short press => blink 'green' for up to SHORT_FLASH_DURATION seconds")
    
    start_time = time.time()  # Record the start time
    flash_state = True         # Initialize the flash state (True for on, False for off)
    wled.flashing = True       # Indicate that flashing is in progress

    press_start_time = None    # Time when a button press starts
    long_press_active = False # Flag to indicate if a long press has been detected

    try:
        # Loop until the short flash duration has elapsed or flashing is stopped
        while (time.time() - start_time < Config.SHORT_FLASH_DURATION) and wled.flashing:
            # Only check for long press during green flashing
            # Short presses are ignored in this loop
            if GPIO.input(Config.BUTTON_PIN) == 0:  # Check if the button is pressed
                if press_start_time is None:
                    press_start_time = time.time()  # Record the time when the button was pressed
                elif (time.time() - press_start_time) >= Config.LONG_PRESS_THRESHOLD and not long_press_active:
                    logging.info("Long press detected during green => switching to red immediately")
                    long_press_active = True  # Set the flag to indicate a long press has been detected
                    # Continue to blink red while the button is held down
                    while GPIO.input(Config.BUTTON_PIN) == 0:
                        interval = Config.FLASH_INTERVAL / 2
                        if flash_state:
                            wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)  # Set color to red
                        else:
                            wled.set_color(0, 0, 0, 0)  # Turn off the LEDs
                        flash_state = not flash_state  # Toggle the flash state
                        time.sleep(interval)  # Wait for the interval before the next flash
                    wled.set_color(255, 255, 255)  # After releasing the button, set LEDs to white
                    return  # Exit the function
            else:
                press_start_time = None  # Reset the press start time if the button is not pressed

            interval = Config.FLASH_INTERVAL / 2  # Calculate the interval between flashes
            if flash_state:
                wled.set_color(0, 255, 0, Config.FLASH_BRIGHTNESS)  # Set color to green
            else:
                wled.set_color(0, 0, 0, 0)  # Turn off the LEDs
            flash_state = not flash_state  # Toggle the flash state
            time.sleep(interval)  # Wait for the interval before the next flash

        wled.set_color(255, 255, 255)  # After flashing, set LEDs to white

    except Exception as e:
        # Log any exceptions that occur during the blinking sequence
        logging.error(f"Error during blink sequence: {e}")
        wled.restore_last_state()  # Attempt to restore the last known state
    finally:
        wled.flashing = False  # Ensure that the flashing flag is reset

def simulate_short_press(wled: WLEDController):
    """
    Simulate a short button press from the web UI.
    This function stops any ongoing flashing and initiates a green blinking sequence.
    Parameters:
        wled (WLEDController): The WLEDController instance to control the LEDs
    """
    logging.info("Simulating short press from web UI.")
    wled.stop_flashing()          # Stop any ongoing flashing
    blink_green_for_30s(wled)     # Start blinking green for a short press

def simulate_long_press(wled: WLEDController):
    """
    Simulate a long button press from the web UI.
    This function initiates a red blinking sequence until the simulated press is released.
    Parameters:
        wled (WLEDController): The WLEDController instance to control the LEDs
    """
    logging.info("Simulating long press from web UI.")

    import RPi.GPIO as GPIO  # Import GPIO here to avoid circular imports
    wled.stop_flashing()     # Stop any ongoing flashing

    hold_start = time.time()  # Record the time when the press starts
    wled.flashing = True      # Indicate that flashing is in progress
    blinking_red = True       # Flag to indicate that red blinking is active
    blink_state = False       # Initial state of the blink (False for off, True for on)
    last_blink_time = time.time()  # Time when the last blink occurred

    try:
        # Loop until blinking_red is False or flashing is stopped
        while blinking_red and wled.flashing:
            threshold = Config.LONG_PRESS_THRESHOLD  # Time threshold for a long press
            interval = Config.FLASH_INTERVAL / 2     # Interval between flashes

            if (time.time() - hold_start) >= threshold:
                # If the hold duration exceeds the threshold, stop blinking red
                blinking_red = False
                wled.set_color(255, 255, 255)  # Set LEDs to white
                logging.info("Simulated long press release => going white")
                break

            now = time.time()  # Current time
            if (now - last_blink_time) >= interval:
                # Toggle the blink state and set the appropriate color
                if blink_state:
                    wled.set_color(0, 0, 0, 0)  # Turn off the LEDs
                else:
                    wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)  # Set color to red
                blink_state = not blink_state  # Toggle the blink state
                last_blink_time = now        # Update the last blink time

            time.sleep(0.01)  # Small sleep to prevent high CPU usage
    except Exception as e:
        # Log any exceptions that occur during the long press simulation
        logging.error(f"Error during long press simulation: {e}")
        wled.restore_last_state()  # Attempt to restore the last known state
    finally:
        wled.flashing = False  # Ensure that the flashing flag is reset

def hardware_button_loop(wled: WLEDController, stop_event: threading.Event):
    """
    Continuously monitor the physical hardware button for presses and handle them accordingly.
    This function runs in a separate thread.
    Parameters:
        wled (WLEDController): The WLEDController instance to control the LEDs
        stop_event (threading.Event): An event to signal when the loop should stop
    """
    import RPi.GPIO as GPIO  # Import GPIO here to avoid circular imports

    GPIO.setmode(GPIO.BCM)  # Set the GPIO numbering mode to BCM
    GPIO.setup(Config.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Set up the button pin with a pull-up resistor

    wled.set_color(255, 255, 255)  # Initialize LEDs to white

    pressed = False           # Flag to indicate if the button is currently pressed
    press_start_time = 0.0    # Time when the button was pressed
    blinking_red = False      # Flag to indicate if red blinking is active
    blink_state = False       # Initial state of the blink (False for off, True for on)
    last_blink_time = 0.0     # Time when the last blink occurred

    while not stop_event.is_set():  # Loop until a stop event is signaled
        if not wled.is_connected:
            # If not connected to WLED, attempt to reconnect
            logging.warning("Lost connection to WLED; attempting reconnect from hardware loop...")
            wled.wait_for_connection()     # Attempt to reconnect
            wled.restore_last_state()      # Restore the last known state

        current_state = GPIO.input(Config.BUTTON_PIN)  # Read the current state of the button

        if not pressed:
            if current_state == 0:
                # Button has been pressed
                pressed = True
                press_start_time = time.time()  # Record the time when the button was pressed
                blinking_red = False            # Reset the red blinking flag
                wled.stop_flashing()            # Stop any ongoing flashing
        else:
            if current_state == 1:
                # Button has been released
                duration = time.time() - press_start_time  # Calculate how long the button was held
                pressed = False

                if blinking_red:
                    # If red blinking was active, set LEDs to white
                    logging.info("Long press released => white")
                    wled.set_color(255, 255, 255)
                    blinking_red = False
                else:
                    threshold = Config.LONG_PRESS_THRESHOLD  # Time threshold for a long press
                    if duration < threshold:
                        # If the press duration is short, initiate a green blinking sequence
                        blink_green_for_30s(wled)
                    else:
                        # If the press duration is long, initiate a red blinking sequence
                        logging.info("Long press ended without in-press blinking => blink red now.")
                        start_t = time.time()
                        flash_state = True
                        wled.flashing = True
                        while (time.time() - start_t < Config.SHORT_FLASH_DURATION) and wled.flashing:
                            interval = Config.FLASH_INTERVAL / 2
                            if flash_state:
                                wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)  # Set color to red
                            else:
                                wled.set_color(0, 0, 0, 0)  # Turn off the LEDs
                            flash_state = not flash_state  # Toggle the flash state
                            time.sleep(interval)
                        wled.set_color(255, 255, 255)  # After flashing, set LEDs to white
                        wled.flashing = False
            else:
                # Button is still being held down
                held_duration = time.time() - press_start_time  # Calculate how long the button has been held
                threshold = Config.LONG_PRESS_THRESHOLD  # Time threshold for a long press
                if (held_duration >= threshold) and not blinking_red:
                    # If the button has been held long enough and red blinking is not active
                    logging.info("Long press threshold reached => blinking red while held down")
                    blinking_red = True
                    blink_state = False
                    last_blink_time = time.time()

                if blinking_red:
                    # Continue blinking red while the button is held down
                    interval = Config.FLASH_INTERVAL / 2
                    now = time.time()
                    if (now - last_blink_time) >= interval:
                        if blink_state:
                            wled.set_color(0, 0, 0, 0)  # Turn off the LEDs
                        else:
                            wled.set_color(255, 0, 0, Config.FLASH_BRIGHTNESS)  # Set color to red
                        blink_state = not blink_state  # Toggle the blink state
                        last_blink_time = now        # Update the last blink time

        time.sleep(0.01)  # Small sleep to prevent high CPU usage

    GPIO.cleanup()  # Clean up the GPIO settings when exiting
    logging.info("Hardware button loop exiting...")

# Initialize the Flask web application
app = Flask(__name__)
stop_event = threading.Event()  # Event to signal threads to stop
wled = None                      # Placeholder for the WLEDController instance

@app.route("/")
def index():
    """
    Route for the home page of the web UI.
    Renders the 'index.html' template and passes the current configuration.
    """
    return render_template("index.html", c=Config)

@app.route("/update_config", methods=["POST"])
def update_config():
    """
    Route to handle updates to the configuration via the web UI.
    Retrieves form data, updates the Config class, writes changes to the INI file,
    and redirects back to the home page.
    """
    form = request.form  # Get the form data submitted via POST

    # Update each configuration parameter from the form data, using existing values as defaults
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

    Config.write_to_ini()  # Write the updated configurations to the INI file
    logging.info("Updated config from web UI. New settings apply immediately in blinking logic.")

    return redirect(url_for("index"))  # Redirect back to the home page

@app.route("/simulate_press", methods=["POST"])
def simulate_press():
    """
    Route to simulate a button press via the web UI.
    Depending on the 'press_type' parameter, it simulates either a short or long press.
    """
    press_type = request.form.get("press_type")  # Get the type of press from the form data
    if press_type == "short":
        simulate_short_press(wled)  # Simulate a short press
    elif press_type == "long":
        simulate_long_press(wled)   # Simulate a long press
    else:
        logging.warning(f"Unknown press type: {press_type}")  # Log a warning for unknown press types
    return redirect(url_for("index"))  # Redirect back to the home page

def background_connect_wled(wled: WLEDController, stop_event: threading.Event):
    """
    Background thread function to continuously attempt to connect to the WLED device.
    This ensures that the application maintains a connection even if it drops.
    Parameters:
        wled (WLEDController): The WLEDController instance to control the LEDs
        stop_event (threading.Event): An event to signal when the thread should stop
    """
    try:
        while not wled.is_connected and not stop_event.is_set():
            wled.wait_for_connection()  # Attempt to connect to the WLED device
    except Exception as e:
        # Log any exceptions that occur in the background connection thread
        logging.error(f"Error in background_connect_wled: {e}")

def main():
    """
    The main function orchestrates the initialization and running of the application.
    It sets up configurations, logging, initializes the WLED controller,
    starts background threads, and runs the Flask web server.
    """
    Config.load_from_ini("blinker-configs.ini")  # Load configurations from the INI file
    setup_logging()                              # Set up logging
    if not Config.validate():
        # If configuration validation fails, log an error and exit
        logging.error("Invalid configuration; exiting.")
        return

    logging.info("Starting WLED Button Flask Application...")  # Log the start of the application

    global wled
    wled = WLEDController(Config.WLED_IP)  # Initialize the WLEDController with the configured IP

    global stop_event
    # Start a background thread to handle connecting to the WLED device
    connect_thread = threading.Thread(
        target=background_connect_wled,
        args=(wled, stop_event),
        daemon=True  # Daemon threads automatically close when the main program exits
    )
    connect_thread.start()  # Start the connection thread

    # Start a hardware button loop in a separate thread to monitor physical button presses
    hardware_thread = threading.Thread(
        target=hardware_button_loop,
        args=(wled, stop_event),
        daemon=True
    )
    hardware_thread.start()  # Start the hardware button thread

    # Run the Flask web server to provide a web interface
    app.run(host="0.0.0.0", port=5000, debug=False)

    # After the Flask server stops, signal threads to stop and perform cleanup
    stop_event.set()              # Signal the threads to stop
    hardware_thread.join()       # Wait for the hardware thread to finish
    connect_thread.join()        # Wait for the connection thread to finish
    wled.cleanup()               # Perform cleanup operations for the WLEDController

# Entry point of the script
if __name__ == "__main__":
    main()  # Call the main function to start the application

