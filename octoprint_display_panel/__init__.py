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

	_area_offset = 3
	_cancel_requested_at = 0
	_cancel_timer = None
	_colored_strip_height = 15 # height of colored strip on top for dual color display
	_debounce = 0
	_display_init = False
	_displaylayerprogress_current_height = -1.0
	_displaylayerprogress_current_layer = -1
	_displaylayerprogress_total_height = -1.0
	_displaylayerprogress_total_layer = -1
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
	_system_stats = {}
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

		# self._logger.info("on_event: %s", event)

		result = self.top_screen.process_event(event, payload)
		if 'DRAW' in result:
			self.update_ui()
		
		self.set_printer_state(event)
#
#		# Connectivity
#		if event == Events.DISCONNECTED:
#			self._screen_mode = ScreenModes.SYSTEM
#
#		if event in (Events.CONNECTED, Events.CONNECTING, Events.CONNECTIVITY_CHANGED,
#								 Events.DISCONNECTING):
#			self.update_ui()
#
#		# Print start display
#		if event == Events.PRINT_STARTED:
#			self._screen_mode = ScreenModes.PRINT
#			self.update_ui()
#
#		# Print end states
#		if event in (Events.PRINT_FAILED, Events.PRINT_DONE, Events.PRINT_CANCELLED,
#								 Events.PRINT_CANCELLING):
#			self._displaylayerprogress_current_height = -1.0
#			self._displaylayerprogress_current_layer = -1
#			self._displaylayerprogress_total_height = -1.0
#			self._displaylayerprogress_total_layer = -1
#			self.update_ui()
#
#		# Print limbo states
#		if event in (Events.PRINT_PAUSED, Events.PRINT_RESUMED):
#			self.update_ui()
#
#		# Mid-print states
#		if event in (Events.Z_CHANGE, Events.PRINTER_STATE_CHANGED):
#			self.update_ui()
#
#		# Get progress information from DisplayLayerProgress plugin
#		if event in ("DisplayLayerProgress_heightChanged",
#						"DisplayLayerProgress_layerChanged"):
#			if payload.get('currentHeight') != "-":
#				self._displaylayerprogress_current_height = float(payload.get('currentHeight'))
#			else:
#				self._displaylayerprogress_current_height = -1.0
#			if payload.get('currentLayer') != "-":
#				self._displaylayerprogress_current_layer = int(payload.get('currentLayer'))
#			else:
#				self._displaylayerprogress_current_layer = -1
#			self._displaylayerprogress_total_height = float(payload.get('totalHeight'))
#			self._displaylayerprogress_total_layer = int(payload.get('totalLayer'))
#			self.update_ui()

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
		Function to check system stats periodically
		"""
		pass
#		self._check_system_timer = RepeatedTimer(5, self.check_system_stats, None, None, True)
#		self._check_system_timer.start()

	def check_system_stats(self):
		"""
		Function to collect general system stats about the underlying system(s).

		Called by the system check timer on a regular basis. This function should remain small,
		performant and not block.
		"""
		pass
#		try:
#			if self._screen_mode == ScreenModes.SYSTEM:
#				s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#				s.connect(("8.8.8.8", 80))
#				self._system_stats['ip'] = s.getsockname()[0]
#				s.close()
#				self._system_stats['load'] = psutil.getloadavg()
#				self._system_stats['memory'] = psutil.virtual_memory()
#				self._system_stats['disk'] = shutil.disk_usage('/') # disk percentage = 100 * used / (used + free)
#
#				self.update_ui()
#			elif self._screen_mode == ScreenModes.PRINTER:
#				# Just update the UI, the printer mode will take care of itself
#				self.update_ui()
#		except Exception as ex:
#			self.log_error(ex)
#			pass

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
		self.top_screen = screens.MicroPanelScreenTop(self.width,
							      self.height)
		
		
	def handle_button_press(self, label):
		"""
		Take action on a button press with the given name (such as 'cancel' or 'play')
		"""
		result = self.top_screen.process_button(label)
		if 'DRAW' in result:
			self.update_ui()
		
#		try:
#			if label == 'cancel':
#				self.try_cancel()
#			else:
#				if self._cancel_timer is not None:
#					self.clear_cancel()
#				else:
#					if label == 'mode':
#						self.next_mode()
#					if label == 'play':
#						self.try_play()
#					if label == 'pause':
#						self.try_pause()
#		except Exception as ex:
#			self.log_error(ex)
#			pass
#
#	def next_mode(self):
#		"""
#		Go to the next screen mode
#		"""
#
#		self._screen_mode = self._screen_mode.next()
#		self.update_ui()
#
#	def try_cancel(self):
#		"""
#		First click, confirm cancellation. Second click, trigger cancel
#		"""
#
#		if not self._printer.is_printing() and not self._printer.is_paused():
#			return
#
#		if self._cancel_timer:
#			# GPIO can double-trigger sometimes, check if this is too fast and ignore
#			if (time.time() - self._cancel_requested_at) < 1:
#				return
#
#			# Cancel has been tried, run a cancel
#			self.clear_cancel()
#			self._printer.cancel_print()
#		else:
#			# First press
#			self._cancel_requested_at = time.time()
#			self._cancel_timer = RepeatedTimer(10, self.clear_cancel, run_first=False)
#			self._cancel_timer.start()
#			self.update_ui()
#
#	def clear_cancel(self):
#		"""
#		Clear a pending cancel, something else was clicked or a timeout occured
#		"""
#
#		if self._cancel_timer:
#			self._cancel_timer.cancel()
#			self._cancel_timer = None
#			self._cancel_requested_at = 0
#			self.update_ui()
#
#	def try_play(self):
#		"""
#		If printer is not connected, try to connect to it.
#		Otherwise, if possible, play or resume a print
#		"""
#
#		if self._printer.get_current_connection()[0] == "Closed":
#			self._printer.connect()
#			return
#
#		current_data = self._printer.get_current_data()
#		if current_data['state']['flags']['ready'] and (current_data['progress']['completion'] or 0) == 0 and current_data['job']['file']['name']:
#			self._printer.start_print()
#			return
#
#		if not self._printer.is_paused():
#			return
#
#		self._printer.resume_print()
#
#	def try_pause(self):
#		"""
#		If possible, pause a running print
#		"""
#
#		if not self._printer.is_printing():
#			return
#
#		self._printer.pause_print()

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
#				current_data = self._printer.get_current_data()
#
#				if self._cancel_timer is not None and current_data['state']['flags']['cancelling'] is False:
#					self.update_ui_cancel_confirm()
#				elif self._screen_mode == ScreenModes.SYSTEM:
#					self.update_ui_system()
#				elif self._screen_mode == ScreenModes.PRINTER:
#					self.update_ui_printer()
#				elif self._screen_mode == ScreenModes.PRINT:
#					self.update_ui_print(current_data)
#
#				self.update_ui_bottom(current_data)

				self.image = self.top_screen.image
				
				# Display image.
				if self._image_rotate:
					self.disp.image(self.image.rotate(angle=180))
				else:
					self.disp.image(self.image)
				self.disp.show()
			except Exception as ex:
				self.log_error(ex)

#	def update_ui_cancel_confirm(self):
#		"""
#		Show a confirmation message that a cancel print has been requested
#		"""
#
#		top = (self._colored_strip_height) * int(self._progress_on_top)
#		bottom = self.height - (self._colored_strip_height * int(not self._progress_on_top))
#		left = 0
#		offset = self._area_offset * int(self._progress_on_top)
#
#		if self._display_init:
#			try:
#				self.draw.rectangle((0, top, self.width, bottom), fill=0)
#
#				display_string = "Cancel Print?"
#				text_width = self.draw.textsize(display_string, font=self.font)[0]
#				self.draw.text((self.width / 2 - text_width / 2, top + offset + 0), display_string, font=self.font, fill=255)
#				display_string = "Press 'X' to confirm"
#				text_width = self.draw.textsize(display_string, font=self.font)[0]
#				self.draw.text((self.width / 2 - text_width / 2, top + offset + 9), display_string, font=self.font, fill=255)
#				display_string = "Press any button or"
#				text_width = self.draw.textsize(display_string, font=self.font)[0]
#				self.draw.text((self.width / 2 - text_width / 2, top + offset + 18), display_string, font=self.font, fill=255)
#				display_string = "wait 10 sec to escape"
#				text_width = self.draw.textsize(display_string, font=self.font)[0]
#				self.draw.text((self.width / 2 - text_width / 2, top + offset + 27), display_string, font=self.font, fill=255)
#			except Exception as ex:
#				self.log_error(ex)
#
#
#	def update_ui_system(self):
#		"""
#		Update three-fourths of the screen with system stats collected by the timed collector
#		"""
#
#		if self._display_init:
#			top = (self._colored_strip_height) * int(self._progress_on_top)
#			bottom = self.height - (self._colored_strip_height * int(not self._progress_on_top))
#			left = 0
#			offset = self._area_offset * int(self._progress_on_top)
#
#			# Draw a black filled box to clear the image.
#			self.draw.rectangle((0, top, self.width, bottom), fill=0)
#
#			try:
#				mem = self._system_stats['memory']
#				disk = self._system_stats['disk']
#
#				# Center IP
#				ip = self._system_stats['ip']
#				tWidth, tHeight = self.draw.textsize(ip)
#				self.draw.text((left + ((self.width - tWidth) / 2), top + offset + 0), ip, font=self.font, fill=255)
#
#				# System Stats
#				self.draw.text((left, top + offset + 9), "L: %s, %s, %s" % self._system_stats['load'], font=self.font, fill=255)
#				self.draw.text((left, top + offset + 18), "M: %s/%s MB %s%%" % (int(mem.used/1048576), int(mem.total/1048576), mem.percent), font=self.font, fill=255)
#				self.draw.text((left, top + offset + 27), "D: %s/%s GB %s%%" % (int(disk.used/1073741824), int((disk.used+disk.total)/1073741824), int(10000*disk.used/(disk.used+disk.free))/100), font=self.font, fill=255)
#			except:
#				self.draw.text((left, top + offset + 9), "Gathering System Stats", font=self.font, fill=255)
#
#	def update_ui_printer(self):
#		"""
#		Update three-fourths of the screen with stats about the printer, such as temperatures
#		"""
#
#		if self._display_init:
#			top = (self._colored_strip_height) * int(self._progress_on_top)
#			bottom = self.height - (self._colored_strip_height * int(not self._progress_on_top))
#			left = 0
#			offset = self._area_offset * int(self._progress_on_top)
#
#			try:
#				self.draw.rectangle((0, top, self.width, bottom), fill=0)
#				self.draw.text((left, top + offset + 0), "Printer Temperatures", font=self.font, fill=255)
#
#				if self._printer.get_current_connection()[0] == "Closed":
#					self.draw.text((left, top + offset + 9), "Head: no printer", font=self.font, fill=255)
#					self.draw.text((left, top + offset + 18), " Bed: no printer", font=self.font, fill=255)
#				else:
#					temperatures = self._printer.get_current_temperatures()
#					tool = temperatures['tool0'] or None
#					bed = temperatures['bed'] or None
#
#					self.draw.text((left, top + offset + 9), "Head: %s / %s\xb0C" % (tool['actual'], tool['target']), font=self.font, fill=255)
#					self.draw.text((left, top + offset + 18), " Bed: %s / %s\xb0C" % (bed['actual'], bed['target']), font=self.font, fill=255)
#			except Exception as ex:
#				self.log_error(ex)
#
#	def update_ui_print(self, current_data):
#		"""
#		Update three-fourths of the screen with information about the current ongoing print
#		"""
#
#		if self._display_init:
#			top = (self._colored_strip_height) * int(self._progress_on_top)
#			bottom = self.height - (self._colored_strip_height * int(not self._progress_on_top))
#			left = 0
#			offset = self._area_offset * int(self._progress_on_top)
#
#			try:
#				self.draw.rectangle((0, top, self.width, bottom), fill=0)
#				self.draw.text((left, top + offset + 0), "State: %s" % (self._printer.get_state_string()), font=self.font, fill=255)
#
#				if current_data['job']['file']['name']:
#					file_name = current_data['job']['file']['name']
#					self.draw.text((left, top + offset + 9), "File: %s" % (file_name), font=self.font, fill=255)
#
#					print_time = self._get_time_from_seconds(current_data['progress']['printTime'] or 0)
#					self.draw.text((left, top + offset + 18), "Time: %s" % (print_time), font=self.font, fill=255)
#
#					filament = current_data['job']['filament']['tool0'] if "tool0" in current_data['job']['filament'] else current_data['job']['filament']
#					filament_length = self.float_count_formatter((filament['length'] or 0) / 1000, 3)
#					filament_mass = self.float_count_formatter(filament['volume'] or 0, 3)
#					self.draw.text((left, top + offset + 27), "Filament: %sm/%scm3" % (filament_length, filament_mass), font=self.font, fill=255)
#
#					# Display height if information available from DisplayLayerProgress plugin
#					height = "{:>5.1f}/{:>5.1f}".format(float(self._displaylayerprogress_current_height), float(self._displaylayerprogress_total_height))
#					layer = "{:>4d}/{:>4d}".format(self._displaylayerprogress_current_layer, self._displaylayerprogress_total_layer)
#					height_text = ""
#					if self._displaylayerprogress_current_height != -1.0 and self._displaylayerprogress_current_layer != -1:
#						height_text = layer + ";" + height
#					elif self._displaylayerprogress_current_layer != -1:
#						height_text = layer
#					elif self._displaylayerprogress_current_height != -1.0:
#						height_text = height
#					self.draw.text((left, top + offset + 36), height_text, font=self.font, fill=255)
#				else:
#					self.draw.text((left, top + offset + 18), "Waiting for file...", font=self.font, fill=255)
#			except Exception as ex:
#				self.log_error(ex)
#
#	def update_ui_bottom(self, current_data):
#		"""
#		Update one-fourths of the screen with persistent information about the current print
#		"""
#
#		if self._display_init:
#			top = (self.height - self._colored_strip_height) * int(not self._progress_on_top)
#			bottom = self.height - ((self.height - self._colored_strip_height) * int(self._progress_on_top))
#			left = 0
#
#			try:
#				# Clear area
#				self.draw.rectangle((0, top, self.width, bottom), fill=0)
#				display_string = ""
#				if self._printer.get_current_connection()[0] == "Closed":
#					# Printer isn't connected
#					display_string = "Printer Not Connected"
#				elif current_data['state']['flags']['paused'] or current_data['state']['flags']['pausing']:
#					# Printer paused
#					display_string = "Paused"
#				elif current_data['state']['flags']['cancelling']:
#					# Printer paused
#					display_string = "Cancelling"
#				elif current_data['state']['flags']['ready'] and (current_data['progress']['completion'] or 0) < 100:
#					# Printer connected, not printing
#					if current_data['job']['file']['name']:
#						display_string = "Ready to Start"
#					else:
#						display_string = "Waiting For Job"
#
#				if display_string:
#					text_width = self.draw.textsize(display_string, font=self.font)[0]
#					self.draw.text((self.width / 2 - text_width / 2, top + 4), display_string, font=self.font, fill=255)
#
#				else:
#					percentage = int(current_data['progress']['completion'] or 0)
#					# Calculate progress from time
#					if current_data['progress']['printTime'] and self._timebased_progress:
#						percentage = int((current_data['progress']['printTime'] or 0) / ((current_data['progress']['printTime'] or 0) + current_data['progress']['printTimeLeft']) * 100)
#					time_left = current_data['progress']['printTimeLeft'] or 0
#
#					# Progress bar
#					self.draw.rectangle((0, top + 0, self.width - 1, top + 5), fill=0, outline=255, width=1)
#					bar_width = int((self.width - 5) * percentage / 100)
#					self.draw.rectangle((2, top + 2, bar_width, top + 3), fill=255, outline=255, width=1)
#
#					# Percentage and ETA
#					self.draw.text((0, top + 5), "%s%%" % (percentage), font=self.font, fill=255)
#					eta = time.strftime(self._eta_strftime, time.localtime(time.time() + time_left))
#					eta_width = self.draw.textsize(eta, font=self.font)[0]
#					self.draw.text((self.width - eta_width, top + 5), eta, font=self.font, fill=255)
#			except Exception as ex:
#				self.log_error(ex)
#
#	# Taken from tpmullan/OctoPrint-DetailedProgress
#	def _get_time_from_seconds(self, seconds):
#		hours = 0
#		minutes = 0
#
#		if seconds >= 3600:
#			hours = int(seconds / 3600)
#			seconds = seconds % 3600
#
#		if seconds >= 60:
#			minutes = int(seconds / 60)
#			seconds = seconds % 60
#
#		return self._etl_format.format(**locals())
#
#	def float_count_formatter(self, number, max_chars):
#		"""
#		Show decimals up to a max number of characters, then flips over and rounds to integer
#		"""
#
#		int_part = "%i" % round(number)
#		if len(int_part) >= max_chars - 1:
#			return int_part
#		elif len("%f" % number) <= max_chars:
#			return "%f" % number
#		else:
#			return "{num:0.{width}f}".format(num=number, width=len(int_part) - 1)

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

