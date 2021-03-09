# coding=utf-8
from __future__ import absolute_import

# system stats
import psutil
import shutil
import socket

import json

import octoprint.plugin
from octoprint.events import eventManager, Events
from octoprint.util import RepeatedTimer, ResettableTimer
import time
from enum import Enum
from board import SCL, SDA
import busio
from PIL import Image, ImageDraw, ImageFont
import inspect
import adafruit_ssd1306
import RPi.GPIO as GPIO

from . import screens

## REFACTORING SCOPES
##   Changes to the following are scoped to a specific branch, and should
##   not be modified by another branch. Conflicting changes should be done
##   in the top-level refactor branch.
##
## refactor/virtual-panel
##   - setup_display(), clear_display()
##   - setup_gpio(), configure_gpio(), configure_single_gpio(), clean_gpio()
##   - handle_gpio_event()
##   - initialize(), get_settings_defaults(), on_settings_save()
##   - bcm2board()
##   - start_display_timer(), stop_display_timer(), trigger_display_timeout()
## refactor/modular-screens
##   - handle_button_press()
##   - next_mode(), try_cancel(), clear_cancel(), try_play(), try_pause()
##   - update_ui() and all other update_ui_***()
##   - _screen_mode, ScreenModes
##   - on_event(), on_print_progress(), on_slicing_progress()
##   - start_system_timer(), check_system_stats()
##   - set_printer_state()

## COMMON INTERFACE
##   The following shall be stable from the top-level refactor branch.
##
## Display_panelPlugin.disp
##   - disp.width, disp.height
##   - disp.fill(n)
##   - disp.show()
##   - disp.poweroff(), disp.poweron()
##   - disp.image(img)
## Display_panelPlugin.handle_button_press(label)
## Display_panelPlugin.update_ui()
## Display_panelPlugin.start_system_timer()
## Display_panelPlugin.start_display_timer(reconfigure)

class ScreenModes(Enum):
	PRINT = 1
	PRINTER = 2
	SYSTEM = 3

	def next(self):
		members = list(self.__class__)
		index = members.index(self) + 1
		if index >= len(members):
			index = 0
		return members[index]

class Display_panelPlugin(octoprint.plugin.StartupPlugin,
                          octoprint.plugin.ShutdownPlugin,
                          octoprint.plugin.EventHandlerPlugin,
                          octoprint.plugin.ProgressPlugin,
                          octoprint.plugin.TemplatePlugin,
                          octoprint.plugin.SettingsPlugin):

	_debounce = 0
	_display_init = False
	_display_timeout_active = False
	_display_timeout_option = 0	# -1 - deactivated, 0 - printer disconnected, 1 - disconnected/connected but idle, 2 - always
	_display_timeout_time = 0
	_display_timeout_timer = None
	_etl_format = "{hours:02d}h {minutes:02d}m {seconds:02d}s"
	_eta_strftime = ""
	_gpio_init = False
	_image_rotate = False
	_last_debounce = 0
	_last_display_timeout_option = 0	# -1 - deactivated, 0 - printer disconnected, 1 - disconnected/connected but idle, 2 - always
	_last_display_timeout_time = 0
	_last_i2c_address = ""
	_last_image_rotate = False
	_last_pin_cancel = -1
	_last_pin_mode = -1
	_last_pin_pause = -1
	_last_pin_play = -1
	_last_printer_state = 0	# 0 - disconnected, 1 - connected but idle, 2 - printing
	_pin_cancel = -1
	_pin_mode = -1
	_pin_pause = -1
	_pin_play = -1
	_printer_state = 0	# 0 - disconnected, 1 - connected but idle, 2 - printing
	_progress_on_top = False
	_screen_mode = ScreenModes.SYSTEM
	_timebased_progress = False

	##~~ StartupPlugin mixin

	def on_after_startup(self):
		"""
		StartupPlugin lifecycle hook, called after Octoprint startup is complete
		"""

		self.setup_display()
		self.setup_screens()
		self.setup_gpio()
		self.configure_gpio()
		self.clear_display()
		self.check_system_stats()
		self.start_system_timer()
		self.update_ui()
		self.start_display_timer()

	##~~ ShutdownPlugin mixin

	def on_shutdown(self):
		"""
		ShutdownPlugin lifecycle hook, called before Octoprint shuts down
		"""

		self.stop_display_timer()
		self.clear_display()
		self.clean_gpio()

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		"""
		EventHandlerPlugin lifecycle hook, called whenever an event is fired
		"""

		#self._logger.info("on_event: %s", event)

		self.set_printer_state(event)
		
		if not hasattr(self, 'top_screen'):
			return
		
		result = self.top_screen.process_event(event, payload)
		if 'DRAW' in result:
			self.update_ui()

	##~~ ProgressPlugin mixin

	def on_print_progress(self, storage, path, progress):
		"""
		ProgressPlugin lifecycle hook, called when print progress changes, at most in 1% incremements
		"""

		self.update_ui()

	def on_slicing_progress(self, slicer, source_location, source_path, destination_location, destination_path, progress):
		"""
		ProgressPlugin lifecycle hook, called whenever slicing progress changes, at most in 1% increments
		"""

		self._logger.info("on_slicing_progress: %s", progress)
		# TODO: Handle slicing progress bar
		self.update_ui()

	##~~ TemplatePlugin mixin
	def get_template_configs(self):
		"""
		TemplatePlugin lifecycle hook, called to get templated settings
		"""

		return [dict(type="settings", custom_bindings=False)]

	##~~ SettingsPlugin mixin

	def initialize(self):
		"""
		Prepare variables for setting modification detection
		"""

		self._debounce = int(self._settings.get(["debounce"]))
		self._display_init = False
		self._display_timeout_option = int(self._settings.get(["display_timeout_option"]))
		self._display_timeout_time = int(self._settings.get(["display_timeout_time"]))
		self._eta_strftime = str(self._settings.get(["eta_strftime"]))
		self._gpio_init = False
		self._i2c_address = str(self._settings.get(["i2c_address"]))
		self._image_rotate = bool(self._settings.get(["image_rotate"]))
		self._pin_cancel = int(self._settings.get(["pin_cancel"]))
		self._pin_mode = int(self._settings.get(["pin_mode"]))
		self._pin_pause = int(self._settings.get(["pin_pause"]))
		self._pin_play = int(self._settings.get(["pin_play"]))
		self._progress_on_top = bool(self._settings.get(["progress_on_top"]))
		self._screen_mode = ScreenModes.SYSTEM
		self._last_debounce = self._debounce
		self._last_display_timeout_option = self._display_timeout_option
		self._last_display_timeout_time = self._display_timeout_time
		self._last_i2c_address = self._i2c_address
		self._last_image_rotate = False
		self._last_pin_cancel = self._pin_cancel
		self._last_pin_mode = self._pin_mode
		self._last_pin_pause = self._pin_pause
		self._last_pin_play = self._pin_play
		self._timebased_progress = bool(self._settings.get(["timebased_progress"]))

	def get_settings_defaults(self):
		"""
		SettingsPlugin lifecycle hook, called to get default settings
		"""

		return dict(
			debounce		= 250,			# Debounce 250ms
			display_timeout_option	= -1,	# Default is never
			display_timeout_time	= 5,	# Default is 5 minutes
			eta_strftime	= "%-m/%d %-I:%M%p",	# Default is month/day hour:minute + AM/PM
			i2c_address		= "0x3c",		# Default is hex address 0x3c
			image_rotate	= False,		# Default if False (no rotation)
			pin_cancel		= -1,			# Default is disabled
			pin_mode		= -1,			# Default is disabled
			pin_pause		= -1,			# Default is disabled
			pin_play		= -1,			# Default is disabled
			progress_on_top	= False,		# Default is disabled
			timebased_progress	= False,	# Default is disabled
		)

	def on_settings_save(self, data):
		"""
		SettingsPlugin lifecycle hook, called when settings are saved
		"""

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self._debounce = int(self._settings.get(["debounce"]))
		self._display_timeout_option = int(self._settings.get(["display_timeout_option"]))
		self._display_timeout_time = int(self._settings.get(["display_timeout_time"]))
		self._eta_strftime = str(self._settings.get(["eta_strftime"]))
		self._i2c_address = str(self._settings.get(["i2c_address"]))
		self._image_rotate = bool(self._settings.get(["image_rotate"]))
		self._pin_cancel = int(self._settings.get(["pin_cancel"]))
		self._pin_mode = int(self._settings.get(["pin_mode"]))
		self._pin_pause = int(self._settings.get(["pin_pause"]))
		self._pin_play = int(self._settings.get(["pin_play"]))
		pins_updated = 0
		try:
			if self._i2c_address.lower() != self._last_i2c_address.lower() or \
			self._image_rotate != self._last_image_rotate:
				self.clear_display()
				self._display_init = False
				self._last_i2c_address = self._i2c_address
				self._last_image_rotate = self._image_rotate
				self.setup_display()
				self.clear_display()
				self.check_system_stats()
				self.start_system_timer()
				self._screen_mode = ScreenModes.SYSTEM
				self.update_ui()

			if self._pin_cancel != self._last_pin_cancel:
				pins_updated = pins_updated + 1
				self.clean_single_gpio(self._last_pin_cancel)
			if self._pin_mode != self._last_pin_mode:
				pins_updated = pins_updated + 2
				self.clean_single_gpio(self._last_pin_mode)
			if self._pin_pause != self._last_pin_pause:
				pins_updated = pins_updated + 4
				self.clean_single_gpio(self._last_pin_pause)
			if self._pin_play != self._last_pin_play:
				pins_updated = pins_updated + 8
				self.clean_single_gpio(self._last_pin_play)

			self._gpio_init = False
			self.setup_gpio()

			if pins_updated == (pow(2, 4) - 1) or self._debounce != self._last_debounce:
				self.configure_gpio()
				pins_updated = 0

			if pins_updated >= pow(2, 3):
				self.configure_single_gpio(self._pin_play)
				pins_updated = pins_updated - pow(2, 3)
			if pins_updated >= pow(2, 2):
				self.configure_single_gpio(self._pin_pause)
				pins_updated = pins_updated - pow(2, 2)
			if pins_updated >= pow(2, 1):
				self.configure_single_gpio(self._pin_mode)
				pins_updated = pins_updated - pow(2, 1)
			if pins_updated >= pow(2, 0):
				self.configure_single_gpio(self._pin_cancel)
				pins_updated = pins_updated - pow(2, 0)
			if pins_updated > 0:
				self.log_error("Something went wrong counting updated GPIO pins")

			if self._display_timeout_option != self._last_display_timeout_option or \
			self._display_timeout_time != self._last_display_timeout_time:
				self.start_display_timer(self._display_timeout_time != self._last_display_timeout_time)

			self._last_debounce = self._debounce
			self._last_display_timeout_option = self._display_timeout_option
			self._last_display_timeout_time = self._display_timeout_time
			self._last_pin_cancel = self._pin_cancel
			self._last_pin_mode = self._pin_mode
			self._last_pin_play = self._pin_play
			self._last_pin_pause = self._pin_pause
		except Exception as ex:
			self.log_error(ex)
			pass

	##~~ Softwareupdate hook

	def get_update_information(self):
		"""
		Softwareupdate hook, standard library hook to handle software update and plugin version info
		"""

		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
		# for details.
		return dict(
			display_panel=dict(
				displayName="OctoPrint Micro Panel",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="sethvoltz",
				repo="OctoPrint-DisplayPanel",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/sethvoltz/OctoPrint-DisplayPanel/archive/{target_version}.zip"
			)
		)

	##~~ Helpers

	def bcm2board(self, bcm_pin):
		"""
		Function to translate bcm pin to board pin
		"""

		board_pin = -1
		if bcm_pin != -1:
			_bcm2board = [
				-1, -1, -1,  7, 29, 31,
				-1, -1, -1, -1, -1, 32,
				33, -1, -1, 36, 11, 12,
				35, 38, 40, 15, 16, 18,
				22, 37, 13
				]
			board_pin=_bcm2board[bcm_pin-1]
		return board_pin

	def start_system_timer(self):
		"""
		Function to refresh the screen periodically
		"""
		self._check_system_timer = RepeatedTimer(5, self.update_ui, None, None, True)
		self._check_system_timer.start()

	def check_system_stats(self):
		"""
		Function to collect general system stats about the underlying system(s).

		Called by the system check timer on a regular basis. This function should remain small,
		performant and not block.
		"""
		pass # Deprecated method, please remove

	def setup_display(self):
		"""
		Intialize display
		"""

		try:
			self.i2c = busio.I2C(SCL, SDA)
			self.disp = adafruit_ssd1306.SSD1306_I2C(128, 64, self.i2c, addr=int(self._i2c_address,0))
			self._logger.info("Setting display to I2C address %s", self._i2c_address)
			self._display_init = True
			self.font = ImageFont.load_default()
			self.width = self.disp.width
			self.height = self.disp.height
			self.image = Image.new("1", (self.width, self.height))
			self.draw = ImageDraw.Draw(self.image)
			self._screen_mode = ScreenModes.SYSTEM
		except Exception as ex:
			self.log_error(ex)
			pass

	def setup_gpio(self):
		"""
		Setup GPIO to use BCM pin numbering, unless already setup in which case fall back and update
		globals to reflect change.
		"""

		self.BCM_PINS = {
			self._pin_mode: 'mode',
			self._pin_cancel: 'cancel',
			self._pin_play: 'play',
			self._pin_pause: 'pause'
			}
		self.BOARD_PINS = {
			self.bcm2board(self._pin_mode) : 'mode',
			self.bcm2board(self._pin_cancel): 'cancel',
			self.bcm2board(self._pin_play): 'play',
			self.bcm2board(self._pin_pause): 'pause'
			}
		self.input_pinset = self.BCM_PINS

		try:
			current_mode = GPIO.getmode()
			set_mode = GPIO.BCM
			if current_mode is None:
				GPIO.setmode(set_mode)
				self.input_pinset = self.BCM_PINS
				self._logger.info("Setting GPIO mode to BCM numbering")
			elif current_mode != set_mode:
				GPIO.setmode(current_mode)
				self.input_pinset = self.BOARD_PINS
				self._logger.info("GPIO mode was already set, adapting to use BOARD numbering")
			GPIO.setwarnings(False)
			self._gpio_init = True
		except Exception as ex:
			self.log_error(ex)
			pass

	def configure_gpio(self):
		"""
		Setup the GPIO pins to handle the buttons as inputs with built-in pull-up resistors
		"""

		if self._gpio_init:
			for gpio_pin in self.input_pinset:
				self.configure_single_gpio(gpio_pin)

	def configure_single_gpio(self, gpio_pin):
		"""
		Setup the GPIO pins to handle the buttons as inputs with built-in pull-up resistors
		"""

		if self._gpio_init:
			try:
				if gpio_pin != -1:
					GPIO.setup(gpio_pin, GPIO.IN, GPIO.PUD_UP)
					GPIO.remove_event_detect(gpio_pin)
					self._logger.info("Adding GPIO event detect on pin %s with edge: FALLING", gpio_pin)
					GPIO.add_event_detect(gpio_pin, GPIO.FALLING, callback=self.handle_gpio_event, bouncetime=self._debounce)
			except Exception as ex:
				self.log_error(ex)

	def clean_gpio(self):
		"""
		Remove event detection and clean up for all pins (`mode`, `cancel`, `play` and `pause`)
		"""

		if self._gpio_init:
			for gpio_pin in self.input_pinset:
				self.clean_single_gpio(gpio_pin)

	def clean_single_gpio(self, gpio_pin):
		"""
		Remove event detection and clean up for all pins (`mode`, `cancel`, `play` and `pause`)
		"""

		if self._gpio_init:
			if gpio_pin!=-1:
				try:
					GPIO.remove_event_detect(gpio_pin)
				except Exception as ex:
					self.log_error(ex)
					pass
				try:
					GPIO.cleanup(gpio_pin)
				except Exception as ex:
					self.log_error(ex)
					pass
				self._logger.info("Removed GPIO pin %s", gpio_pin)

	def handle_gpio_event(self, channel):
		"""
		Event callback for GPIO event, called from `add_event_detect` setup in `configure_gpio`
		"""

		try:
			if channel in self.input_pinset:
				if self._display_timeout_active:
					self.start_display_timer()
					return
				else:
					self.start_display_timer()
				label = self.input_pinset[channel]

				self.handle_button_press(label)
		except Exception as ex:
			self.log_error(ex)
			pass

	def setup_screens(self):
		"""Create the top level screen.
		"""
		self._logger.info("Initializing screens...")
		try:
		        self.top_screen = screens.MicroPanelScreenTop(
			        self.width, self.height,
			        self._printer, self._settings
		        )
		except:
			self._logger.exception("Failed to initialize screen")
			self.top_screen = screens.MessageScreen(
				self.width, self.height,
				"Failed to initialize,\ncheck OctoPrint log"
			)
		
	def handle_button_press(self, label):
		"""
		Take action on a button press with the given name (such as 'cancel' or 'play')
		"""
		try:
			result = self.top_screen.process_button(label)
			if 'DRAW' in result:
				self.update_ui()
		except:
			self._logger.exception(f'Pressed button {label}')

	def clear_display(self):
		"""
		Clear the OLED display completely. Used at startup and shutdown to ensure a blank screen
		"""

		if self._display_init:
			self.disp.fill(0)
			self.disp.show()

	def set_printer_state(self, event):
		"""
		Set printer state based on latest event
		"""

		if event in (Events.DISCONNECTED, Events.CONNECTED,
					 Events.PRINT_STARTED, Events.PRINT_FAILED,
					 Events.PRINT_DONE, Events.PRINT_CANCELLED,
					 Events.PRINT_PAUSED, Events.PRINT_RESUMED):
			if event == Events.DISCONNECTED:
				self._printer_state = 0
			if event in (Events.CONNECTED, Events.PRINT_FAILED,
						 Events.PRINT_DONE, Events.PRINT_CANCELLED,
						 Events.PRINT_PAUSED):
				self._printer_state = 1
			if event in (Events.PRINT_STARTED, Events.PRINT_RESUMED):
				self._printer_state = 2

			if self._printer_state != self._last_printer_state:
				self.start_display_timer(True)
				self._last_printer_state = self._printer_state
		return

	def start_display_timer(self, reconfigure=False):
		"""
		Start timer for display timeout
		"""

		do_reset = False
		if self._display_timeout_timer is not None:
			if reconfigure:
				self.stop_display_timer()
			else:
				do_reset = True

		if do_reset:
			self._display_timeout_timer.reset()
		else:
			if self._printer_state <= self._display_timeout_option:
				self._display_timeout_timer = ResettableTimer(self._display_timeout_time * 60, self.trigger_display_timeout, [True], None, True)
				self._display_timeout_timer.start()
			if self._display_timeout_active:
				self.trigger_display_timeout(False)
		return

	def stop_display_timer(self):
		"""
		Stop timer for display timeout
		"""

		if self._display_timeout_timer is not None:
			self._display_timeout_timer.cancel()
			self._display_timeout_timer = None
		return

	def trigger_display_timeout(self, activate):
		"""
		Set display off on activate == True and on on activate == False
		"""

		self._display_timeout_active = activate
		if self._display_init:
			if activate:
				self.stop_display_timer()
				self.disp.poweroff()
			else:
				self.disp.poweron()
		return

	def update_ui(self):
		"""
		Update the on-screen UI based on the current screen mode and printer status
		"""

		
		if self._display_init:
			try:
				self.image = self.top_screen.image
				
				# Display image.
				if self._image_rotate:
					self.disp.image(self.image.rotate(angle=180))
				else:
					self.disp.image(self.image)
				self.disp.show()
			except Exception as ex:
				self.log_error(ex)

	def log_error(self, ex):
		"""
		Helper function for more complete logging on exceptions
		"""

		template = "An exception of type {0} occurred on {1}. Arguments: {2!r}"
		message = template.format(type(ex).__name__, inspect.currentframe().f_code.co_name, ex.args)
		self._logger.warn(message)

__plugin_name__ = "OctoPrint Micro Panel"
__plugin_pythoncompat__ = ">=3,<4" # only python 3

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = Display_panelPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

