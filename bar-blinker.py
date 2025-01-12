"""
WLED Button Controller for Raspberry Pi
---------------------------------------

This script allows a Raspberry Pi to communicate with a WLED device (running on an ESP8266 or ESP32)
to control a strip of addressable LEDs. The Raspberry Pi reads a physical button input on GPIO pin 18.
When the button is pressed, the script triggers a green flashing pattern on the LEDs, then returns them
to white. It also includes logic for reconnecting to the WLED device if the connection fails.

Hardware Requirements:
    - Raspberry Pi (any model)
    - A physical push-button wired between GPIO 18 and GND
    - A WLED device (ESP8266/ESP32) with addressable LEDs
    - Network connectivity between Raspberry Pi and WLED device

Usage Steps:
    1. Connect the button to GPIO 18 and GND on the Raspberry Pi.
    2. Set the WLED_IP variable below to match your WLED device’s IP address.
    3. Run this script on the Raspberry Pi (e.g., 'python3 wled_button_controller.py').
    4. Press the button to trigger the flashing sequence.

Important Notes:
    - The script uses the 'requests' library to send HTTP requests to the WLED device.
    - The script uses 'RPi.GPIO' to handle GPIO operations on the Raspberry Pi.
    - Logging is configured to use a rotating file log: /var/log/wled_button.log
    - If connection to the WLED device is lost, it will repeatedly attempt reconnection.
"""

import RPi.GPIO as GPIO  # Library for Raspberry Pi GPIO pin control
import requests          # Library for sending HTTP requests
import time              # Library for time-related functions (sleep, current time, etc.)
import json              # Library for handling JSON data
import logging           # Python's built-in logging library
import logging.handlers  # Used for log rotation
import os               # Library for operating system related functions (paths, directories, etc.)
import socket           # Library for low-level networking (not extensively used here)
from datetime import datetime  # Library for date/time operations in logging or timestamp

# ------------------- Configuration Section -------------------

BUTTON_PIN = 18             # The GPIO pin number (BCM notation) where the button is connected.
WLED_IP = "192.168.1.100"   # The IP address of your WLED device on the network.
FLASH_DURATION = 30         # The number of seconds the LED strip will flash green.
FLASH_INTERVAL = 0.5        # The interval (in seconds) between flash toggles (green -> off -> green).
FLASH_BRIGHTNESS = 255      # The brightness (0-255) for the flashing lights.
LOG_FILE = "/var/log/wled_button.log"  # Path to the log file where logs are written and rotated.
MAX_RETRIES = 3             # Number of retries for sending a command to the WLED device before giving up.
RETRY_DELAY = 1             # Wait time (in seconds) between retries.
RECONNECT_DELAY = 5         # Wait time (in seconds) before attempting a reconnect if WLED is not reachable.
TRANSITION_TIME = 0.0       # Time (in seconds) to transition between color changes (0 = instant).

# -------------------------------------------------------------

class WLEDController:
    """
    A class that encapsulates all interactions with the WLED device.

    Attributes:
        ip_address (str): The IP address of the WLED device.
        led_count (int): Number of LEDs in the attached strip (obtained from the WLED device info).
        name (str): The user-defined name of the WLED device (obtained from WLED).
        version (str): The firmware version of the WLED device.
        is_connected (bool): Indicates whether a successful connection to WLED has been established.
        _last_state (dict): Stores the last known good state (color/brightness/segment settings).
        flashing (bool): A flag that indicates whether a flashing sequence is currently in progress.
    """

    def __init__(self, ip_address):
        """
        Constructor for the WLEDController class.

        Args:
            ip_address (str): The IP address of the WLED device.
        """
        self.ip_address = ip_address
        self.led_count = 0
        self.name = "Unknown"
        self.version = "Unknown"
        self.is_connected = False
        self._last_state = None
        self.flashing = False

    def wait_for_connection(self):
        """
        Attempts to connect to the WLED device repeatedly until a successful connection is established.

        Returns:
            bool: True if a connection is eventually made, False otherwise.
                  (In this script, it will keep trying indefinitely until it succeeds.)
        """
        attempt = 1  # Used to track how many times we've tried to connect
        while not self.is_connected:
            logging.info(f"Connection attempt {attempt}...")
            if self.initialize():
                # If connection is successful (initialize returns True), break out.
                return True
            attempt += 1
            time.sleep(RECONNECT_DELAY)  # Wait a few seconds before trying again
        return True

    def initialize(self):
        """
        Attempts to initialize the connection by fetching device info from WLED.

        This method calls 'get_info' to retrieve information about the device. If successful,
        it updates local attributes (led_count, name, version) and sets is_connected to True.

        Returns:
            bool: True if the device info was successfully retrieved, False otherwise.
        """
        info = self.get_info()
        if info:
            # Extract LED count, device name, and version from the info returned by WLED
            self.led_count = info.get('leds', {}).get('count', 0)
            self.name = info.get('name', 'Unknown')
            self.version = info.get('ver', 'Unknown')
            self.is_connected = True
            logging.info(f"Connected to {self.name}, {self.led_count} LEDs")
            return True
        self.is_connected = False
        return False

    def get_info(self):
        """
        Sends a GET request to the WLED device to retrieve JSON info.

        URL used:
            http://<ip_address>/json/info

        Returns:
            dict or None: If the request is successful and returns status code 200, returns a dictionary
                          with information about the WLED device (LED count, name, version, etc.).
                          Otherwise, returns None.
        """
        try:
            # Send a GET request to WLED's /json/info endpoint.
            response = requests.get(f"http://{self.ip_address}/json/info", timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to get WLED info: {e}")
            return None

    def set_color(self, red, green, blue, brightness=255):
        """
        Sets the color and brightness of the entire LED strip.

        This method constructs a JSON payload that WLED understands, which includes:
        - The on/off state (set to True)
        - The brightness level
        - The transition time (converted to milliseconds)
        - A single segment configuration (seg[0]) with the desired color.

        Args:
            red (int): Red component (0-255).
            green (int): Green component (0-255).
            blue (int): Blue component (0-255).
            brightness (int): The overall brightness (0-255).

        Returns:
            bool: True if the state update was successful, False otherwise.
        """
        if not self.is_connected or self.led_count == 0:
            # If we're not currently connected or the LED count is zero, we can't set color.
            return False

        # Create a dictionary that matches the WLED JSON API format for /json/state
        state = {
            "on": True,
            "bri": brightness,
            "transition": int(TRANSITION_TIME * 1000),  # Convert transition time to milliseconds
            "seg": [{
                "id": 0,
                "col": [[red, green, blue]],  # Nested list for color as per WLED JSON format
                "fx": 0,  # Effect index (0 = Solid)
                "sx": 0,  # Effect speed
                "ix": 0   # Effect intensity
            }]
        }

        success = self._send_state(state)
        if success:
            self._last_state = state  # Save the state if sending was successful
        return success

    def _send_state(self, state):
        """
        Sends a POST request to WLED's /json/state endpoint with retry logic.

        If a request fails, it will retry up to MAX_RETRIES times. Between attempts,
        it waits RETRY_DELAY seconds. If all attempts fail, is_connected is set to False.

        Args:
            state (dict): The JSON payload (Python dictionary) to send to the WLED device.

        Returns:
            bool: True if the HTTP POST response has status code 200, False otherwise.
        """
        url = f"http://{self.ip_address}/json/state"

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(url, json=state, timeout=5)
                if response.status_code == 200:
                    # State update success
                    return True
                logging.warning(f"Failed to set state (Attempt {attempt + 1})")
            except requests.exceptions.RequestException as e:
                logging.warning(f"Error: {e}")
                # If a request fails at the network layer, mark is_connected as False
                self.is_connected = False

            # If we're not on the last attempt, wait and then retry
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
        return False

    def flash_sequence(self, flash_duration):
        """
        Runs a green flashing sequence for the specified duration.

        The sequence alternates between green (0, 255, 0) and 'off' (0, 0, 0 at 0 brightness),
        pausing FLASH_INTERVAL / 2 seconds between toggles. If the flash is stopped externally
        (by calling stop_flashing), this method will exit early.

        Args:
            flash_duration (float): The total time (in seconds) to flash.

        Returns:
            bool: True if it completes the flashing sequence, False if interrupted or an error occurs.
        """
        self.flashing = True  # Set the flashing flag to True
        start_time = time.time()  # Record the current time to compare how long we've been flashing
        flash_state = True        # This is a toggle to alternate between green and off

        try:
            # Keep flashing until we've reached flash_duration seconds OR until self.flashing is False
            while (time.time() - start_time < flash_duration) and self.flashing:
                if flash_state:
                    # Set color to green
                    success = self.set_color(0, 255, 0, FLASH_BRIGHTNESS)
                else:
                    # Turn the strip 'off' by setting brightness to 0
                    success = self.set_color(0, 0, 0, 0)

                if not success:
                    # If we fail to set color, stop flashing and return False
                    self.flashing = False
                    return False

                # Wait for half the FLASH_INTERVAL before toggling again
                time.sleep(FLASH_INTERVAL / 2)

                # Toggle flash_state
                flash_state = not flash_state

            # If we exit the loop normally, turn off the flashing flag
            self.flashing = False
            return True

        except Exception as e:
            # In case of any unexpected exception, log an error and stop flashing
            logging.error(f"Flash sequence error: {e}")
            self.flashing = False
            return False

    def stop_flashing(self):
        """
        Sets the flashing flag to False, which instructs any ongoing flash_sequence() to stop.

        This method does not immediately reset the LEDs; it simply stops the current flash loop.
        """
        self.flashing = False

    def restore_last_state(self):
        """
        Attempts to restore the last known good LED state (if any exists).

        Returns:
            bool: True if the last state was successfully restored, False otherwise.
        """
        if self._last_state:
            logging.info("Restoring last state")
            return self._send_state(self._last_state)
        return False

    def save_state(self):
        """
        Sends a request to WLED to save the current state as Preset 1.

        The payload {"ps": 1, "save": True} instructs WLED to save the current state into preset slot 1.
        This can be useful if you want to quickly restore the same state later from the WLED interface.

        Returns:
            bool: True if the preset was successfully saved, False otherwise.
        """
        try:
            url = f"http://{self.ip_address}/json/state"
            # 'ps': 1 indicates "Preset Slot 1", 'save': True instructs WLED to store current state
            response = requests.post(url, json={"ps": 1, "save": True}, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to save state: {e}")
            self.is_connected = False
            return False


def setup_logging():
    """
    Configures logging to use a rotating file handler.

    The log file is defined by LOG_FILE (default: /var/log/wled_button.log).
    If the directory does not exist, this function attempts to create it.
    Logs are rotated every 1 MB, keeping up to 5 backups.

    Returns:
        logging.Logger: The logger instance that was configured.
    """
    try:
        # Ensure the directory for the log file exists
        log_dir = os.path.dirname(LOG_FILE)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Create a rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=1024 * 1024,  # 1 MB
            backupCount=5          # Keep up to 5 backup files
        )

        # Create a log message format that includes timestamp, level, and message
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)

        # Get the root logger and attach our rotating file handler
        logger = logging.getLogger()
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        return logger
    except Exception as e:
        # If something goes wrong, set up basic logging to console as a fallback
        logging.basicConfig(level=logging.INFO)
        logging.error(f"Logging setup failed: {e}")
        return logging.getLogger()


def cleanup():
    """
    Cleans up the GPIO resources used by the script.

    This function should be called upon exit to ensure GPIO pins are reset.
    """
    try:
        GPIO.cleanup()
        logging.info("GPIO cleanup completed")
    except Exception as e:
        logging.error(f"Cleanup error: {e}")


def main():
    """
    The main entry point of the script.

    This function:
        1. Sets up logging
        2. Initializes the WLEDController
        3. Configures the Raspberry Pi GPIO pin for input (BUTTON_PIN)
        4. Waits for WLED connection and sets initial LED color to white
        5. Saves this initial white state as a preset (optional)
        6. Defines a callback function for button presses
        7. Adds an event detect on GPIO to call the button callback
        8. Enters an infinite loop to keep the script running, periodically checking connection

    When the user presses CTRL+C, the script catches it, stops any flashing in progress, and cleans up.
    """
    logger = setup_logging()  # Configure logging and get the logger instance
    logging.info("WLED Button Control Starting...")

    # Instantiate the WLEDController with the IP address of your WLED device
    wled = WLEDController(WLED_IP)

    try:
        # Set up the GPIO mode. BCM means we refer to GPIO pins by their "Broadcom SOC channel" numbers.
        GPIO.setmode(GPIO.BCM)

        # Configure the button pin as an input with an internal pull-up resistor.
        # The button should be wired to ground, so pressing the button brings the input to LOW (0).
        GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        logging.info(f"GPIO initialized on pin {BUTTON_PIN}")

        # Attempt to connect to the WLED device indefinitely until successful.
        wled.wait_for_connection()

        # Set the LEDs to white (255, 255, 255) as the initial state.
        if not wled.set_color(255, 255, 255):
            logging.error("Failed to set initial white color")

        # Save this white state as WLED preset 1 for future reference.
        if wled.save_state():
            logging.info("Saved initial state to preset 1")

        def button_callback(channel):
            """
            Callback function that is automatically called when the button is pressed.

            This function will:
                1. Log that the button was pressed
                2. Ensure the WLED device is connected
                3. Stop any ongoing flash sequence
                4. Execute a green flash sequence for FLASH_DURATION seconds
                5. Attempt to restore white color or fallback to last known state
            """
            try:
                logging.info("Button press detected")

                # If the WLED device isn't connected, try to initialize again.
                if not wled.is_connected and not wled.initialize():
                    logging.error("WLED device not connected")
                    return

                # Stop any ongoing flashing to avoid conflicts.
                wled.stop_flashing()

                # Run the green flashing sequence.
                if wled.flash_sequence(FLASH_DURATION):
                    # After flashing completes, set color back to white.
                    if not wled.set_color(255, 255, 255):
                        logging.error("Failed to restore white")
                        # If setting white fails, attempt restoring the last known state.
                        wled.restore_last_state()
                else:
                    # If the flash sequence was interrupted or failed, restore last known state.
                    logging.error("Flash sequence interrupted")
                    wled.restore_last_state()

            except Exception as e:
                # If there's an unhandled exception in the callback, log it and stop flashing.
                logging.error(f"Button callback error: {e}")
                wled.stop_flashing()

        # Detect falling edge on the button pin.
        # Falling edge means the pin goes from HIGH to LOW, which happens when the button is pressed.
        GPIO.add_event_detect(
            BUTTON_PIN,
            GPIO.FALLING,
            callback=button_callback,
            bouncetime=300  # Debounce time in milliseconds (prevents multiple triggers)
        )
        logging.info("Button detection enabled")

        # Keep the script running indefinitely. The button_callback will handle button presses.
        # We also check periodically if the WLED connection is still active, and if not, reconnect.
        while True:
            if not wled.is_connected:
                logging.warning("Lost connection to WLED")
                wled.wait_for_connection()
                # After reconnecting, try to restore the last known state.
                wled.restore_last_state()
            time.sleep(5)

    except KeyboardInterrupt:
        # If the user presses CTRL+C, we log a message and exit gracefully.
        logging.info("Program stopped by user")
        wled.stop_flashing()
    except Exception as e:
        # Catch any other unexpected exceptions and log them.
        logging.error(f"Unexpected error: {e}")
    finally:
        # The 'finally' block executes even if an exception occurs.
        # We clean up GPIO resources to avoid leaving pins in an undefined state.
        cleanup()


# This is the standard Python idiom that checks if this file is being run as a script,
# and if so, calls the main() function. Otherwise, if it's just imported, main() won't be called.
if __name__ == "__main__":
    main()
