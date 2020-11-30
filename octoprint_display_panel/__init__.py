# coding=utf-8
from __future__ import absolute_import

# system stats 
import psutil
import shutil
import socket

import json

import octoprint.plugin
from octoprint.events import eventManager, Events
from octoprint.util import RepeatedTimer
import time
from enum import Enum
from board import SCL, SDA
import busio
from PIL import Image, ImageDraw, ImageFont
import inspect
import adafruit_ssd1306
import RPi.GPIO as GPIO

class ScreenMode(Enum):
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
                          octoprint.plugin.ProgressPlugin):

	BCM_PINS = { 4: 'mode', 22: 'cancel', 17: 'play', 27: 'pause' }
	BOARD_PINS = { 7: 'mode', 15: 'cancel', 11: 'play', 13: 'pause' }

	screen_mode = ScreenMode.SYSTEM
	input_pinset = BCM_PINS

	system_stats = {}
	i2c = busio.I2C(SCL, SDA)
	disp = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)
	font = ImageFont.load_default()
	width = disp.width
	height = disp.height
	image = Image.new("1", (width, height))
	draw = ImageDraw.Draw(image)
	bottom_height = 22

	_cancel_timer = None
	_cancel_requested_at = 0
	_eta_strftime = "%-m/%d %-I:%M%p"
	_etl_format = "{hours:02d}h {minutes:02d}m {seconds:02d}s"

	##~~ StartupPlugin mixin

	def on_after_startup(self):
		"""
		StartupPlugin lifecycle hook, called after Octoprint startup is complete
		"""

		self.setup_gpio()
		self.configure_gpio()
		self.clear_display()
		self.check_system_stats()
		self.start_system_timer()
		self.screen_mode = ScreenMode.SYSTEM
		self.update_ui()

	##~~ ShutdownPlugin mixin

	def on_shutdown(self):
		"""
		ShutdownPlugin lifecycle hook, called before Octoprint shuts down
		"""

		self.clear_display()

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		"""
		EventHandlerPlugin lifecycle hook, called whenever an event is fired
		"""

		# self._logger.info("on_event: %s", event)
		
		# Connectivity
		if event in (Events.CONNECTED, Events.CONNECTING, Events.CONNECTIVITY_CHANGED,
								 Events.DISCONNECTED, Events.DISCONNECTING):
			self.update_ui()
		
		# Print start display
		if event == Events.PRINT_STARTED:
			self.screen_mode = ScreenMode.PRINT
			self.update_ui()
		
		# Print end states
		if event in (Events.PRINT_FAILED, Events.PRINT_DONE, Events.PRINT_CANCELLED,
								 Events.PRINT_CANCELLING):
			self.update_ui()

		# Print limbo states
		if event in (Events.PRINT_PAUSED, Events.PRINT_RESUMED):
			self.update_ui()

		# Mid-print states
		if event in (Events.Z_CHANGE, Events.PRINTER_STATE_CHANGED):
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
				displayName="Display Panel Plugin",
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

	def start_system_timer(self):
		"""
		Function to check system stats periodically
		"""

		self._check_system_timer = RepeatedTimer(5, self.check_system_stats, None, None, True)
		self._check_system_timer.start()

	def check_system_stats(self):
		"""
		Function to collect general system stats about the underlying system(s).
		
		Called by the system check timer on a regular basis. This function should remain small,
		performant and not block.
		"""

		if self.screen_mode == ScreenMode.SYSTEM:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			s.connect(("8.8.8.8", 80))
			self.system_stats['ip'] = s.getsockname()[0]
			s.close()
			self.system_stats['load'] = psutil.getloadavg()
			self.system_stats['memory'] = psutil.virtual_memory()
			self.system_stats['disk'] = shutil.disk_usage('/') # disk percentage = 100 * used / (used + free)

			self.update_ui()
		elif self.screen_mode == ScreenMode.PRINTER:
			# Just update the UI, the printer mode will take care of itself
			self.update_ui()

	def setup_gpio(self):
		"""
		Setup GPIO to use BCM pin numbering, unless already setup in which case fall back and update
		globals to reflect change.
		"""
		
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
		except Exception as ex:
			self.log_error(ex)
	
	def configure_gpio(self):
		"""
		Setup the GPIO pins to handle the buttons as inputs with built-in pull-up resistors
		"""
		
		try:
			for gpio_pin in self.input_pinset:
				GPIO.setup(gpio_pin, GPIO.IN, GPIO.PUD_UP)
				GPIO.remove_event_detect(gpio_pin)
				self._logger.info("Adding GPIO event detect on pin %s with edge: FALLING", gpio_pin)
				GPIO.add_event_detect(gpio_pin, GPIO.FALLING, callback=self.handle_gpio_event, bouncetime=250)
		except Exception as ex:
			self.log_error(ex)

	def handle_gpio_event(self, channel):
		"""
		Event callback for GPIO event, called from `add_event_detect` setup in `configure_gpio`
		"""
		
		try:
			if channel in self.input_pinset:
				label = self.input_pinset[channel]
				if label == 'cancel':
					self.try_cancel()
				else:
					if self._cancel_timer is not None:
						self.clear_cancel()
					else:
						if label == 'mode':
							self.next_mode()
						if label == 'play':
							self.try_play()
						if label == 'pause':
							self.try_pause()
		except Exception as ex:
			self.log_error(ex)
			pass

	def next_mode(self):
		"""
		Go to the next screen mode
		"""

		self.screen_mode = self.screen_mode.next()
		self.update_ui()

	def try_cancel(self):
		"""
		First click, confirm cancellation. Second click, trigger cancel
		"""

		if not self._printer.is_printing() and not self._printer.is_paused():
			return

		if self._cancel_timer:
			# GPIO can double-trigger sometimes, check if this is too fast and ignore
			if (time.time() - self._cancel_requested_at) < 1:
				return

			# Cancel has been tried, run a cancel
			self.clear_cancel()
			self._printer.cancel_print()
		else:
			# First press
			self._cancel_requested_at = time.time()
			self._cancel_timer = RepeatedTimer(10, self.clear_cancel, run_first=False)
			self._cancel_timer.start()
			self.update_ui()

	def clear_cancel(self):
		"""
		Clear a pending cancel, something else was clicked or a timeout occured
		"""

		if self._cancel_timer:
			self._cancel_timer.cancel()
			self._cancel_timer = None
			self._cancel_requested_at = 0
			self.update_ui()

	def try_play(self):
		"""
		If possible, play or resume a print
		"""

		# TODO: If a print is queued up and ready, start it
		if not self._printer.is_paused():
			return
		
		self._printer.resume_print()
	
	def try_pause(self):
		"""
		If possible, pause a running print
		"""

		if not self._printer.is_printing():
			return
		
		self._printer.pause_print()
	
	def clear_display(self):
		"""
		Clear the OLED display completely. Used at startup and shutdown to ensure a blank screen
		"""
		
		self.disp.fill(0)
		self.disp.show()

	def update_ui(self):
		"""
		Update the on-screen UI based on the current screen mode and printer status
		"""

		try:
			current_data = self._printer.get_current_data()
			
			if self._cancel_timer is not None and current_data['state']['flags']['cancelling'] is False:
				self.update_ui_cancel_confirm()
			elif self.screen_mode == ScreenMode.SYSTEM:
				self.update_ui_system()
			elif self.screen_mode == ScreenMode.PRINTER:
				self.update_ui_printer()
			elif self.screen_mode == ScreenMode.PRINT:
				self.update_ui_print(current_data)
			
			self.update_ui_bottom(current_data)

			# Display image.
			self.disp.image(self.image)
			self.disp.show()
		except Exception as ex:
			self.log_error(ex)
	
	def update_ui_cancel_confirm(self):
		"""
		Show a confirmation message that a cancel print has been requested
		"""

		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		try:
			self.draw.rectangle((0, 0, self.width, bottom), fill=0)

			display_string = "Cancel Print?"
			text_width = self.draw.textsize(display_string, font=self.font)[0]
			self.draw.text((self.width / 2 - text_width / 2, top + 0), display_string, font=self.font, fill=255)
			display_string = "Press 'X' to confirm"
			text_width = self.draw.textsize(display_string, font=self.font)[0]
			self.draw.text((self.width / 2 - text_width / 2, top + 9), display_string, font=self.font, fill=255)
			display_string = "Press any button or"
			text_width = self.draw.textsize(display_string, font=self.font)[0]
			self.draw.text((self.width / 2 - text_width / 2, top + 18), display_string, font=self.font, fill=255)
			display_string = "wait 10 sec to escape"
			text_width = self.draw.textsize(display_string, font=self.font)[0]
			self.draw.text((self.width / 2 - text_width / 2, top + 27), display_string, font=self.font, fill=255)
		except Exception as ex:
			self.log_error(ex)

	
	def update_ui_system(self):
		"""
		Update the upper two-thirds of the screen with system stats collected by the timed collector
		"""
		
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		# Draw a black filled box to clear the image.
		self.draw.rectangle((0, 0, self.width, bottom), fill=0)

		try:
			mem = self.system_stats['memory']
			disk = self.system_stats['disk']
			# Write four lines of text.
			self.draw.text((left, top + 0), "IP: %s" % (self.system_stats['ip']), font=self.font, fill=255)
			self.draw.text((left, top + 9), "Load: %s, %s, %s" % self.system_stats['load'], font=self.font, fill=255)
			self.draw.text((left, top + 18), "Mem: %s/%s MB %s%%" % (int(mem.used/1048576), int(mem.total/1048576), mem.percent), font=self.font, fill=255)
			self.draw.text((left, top + 27), "Disk: %s/%s GB %s%%" % (int(disk.used/1073741824), int((disk.used+disk.total)/1073741824), int(10000*disk.used/(disk.used+disk.free))/100), font=self.font, fill=255)
		except:
			self.draw.text((left, top + 9), "Gathering System Stats", font=self.font, fill=255)

	def update_ui_printer(self):
		"""
		Update the upper two-thirds of the screen with stats about the printer, such as temperatures
		"""
		
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		try:
			temperatures = self._printer.get_current_temperatures()
			tool = temperatures['tool0'] or None
			bed = temperatures['bed'] or None

			self.draw.rectangle((0, 0, self.width, bottom), fill=0)
			self.draw.text((left, top + 0), "Printer Temperatures", font=self.font, fill=255)
			self.draw.text((left, top + 9), "Head: %s / %s ºC" % (tool['actual'], tool['target']), font=self.font, fill=255)
			self.draw.text((left, top + 18), " Bed: %s / %s ºC" % (bed['actual'], bed['target']), font=self.font, fill=255)
		except Exception as ex:
			self.log_error(ex)

	def update_ui_print(self, current_data):
		"""
		Update the upper two-thirds of the screen with information about the current ongoing print
		"""
		
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		try:
			self.draw.rectangle((0, 0, self.width, bottom), fill=0)
			self.draw.text((left, top + 0), "State: %s" % (self._printer.get_state_string()), font=self.font, fill=255)

			if current_data['job']['file']['name']:
				file_name = current_data['job']['file']['name']
				self.draw.text((left, top + 9), "File: %s" % (file_name), font=self.font, fill=255)

				print_time = self._get_time_from_seconds(current_data['progress']['printTime'] or 0)
				self.draw.text((left, top + 18), "Time: %s" % (print_time), font=self.font, fill=255)

				filament = current_data['job']['filament']['tool0'] if "tool0" in current_data['job']['filament'] else current_data['job']['filament']
				filament_length = int((filament['length'] or 0) / 100) / 10
				filament_mass = int((filament['volume'] or 0) * 10) / 10
				self.draw.text((left, top + 27), "Filament: %sm/%scm3" % (filament_length, filament_mass), font=self.font, fill=255)
			else:
				self.draw.text((left, top + 18), "Waiting for file...", font=self.font, fill=255)
		except Exception as ex:
			self.log_error(ex)
	
	def update_ui_bottom(self, current_data):
		"""
		Update the bottom third of the screen with persistent information about the current print
		"""
		
		top = self.height - self.bottom_height
		bottom = self.height
		left = 0

		try:
			# Clear area
			self.draw.rectangle((0, top, self.width, bottom), fill=0)

			if self._printer.get_current_connection()[0] == "Closed":
				# Printer isn't connected
				display_string = "Printer Not Connected"
				text_width = self.draw.textsize(display_string, font=self.font)[0]
				self.draw.text((self.width / 2 - text_width / 2, top + 6), display_string, font=self.font, fill=255)
			
			elif current_data['state']['flags']['paused'] or current_data['state']['flags']['pausing']:
				# Printer paused
				display_string = "Paused"
				text_width = self.draw.textsize(display_string, font=self.font)[0]
				self.draw.text((self.width / 2 - text_width / 2, top + 6), display_string, font=self.font, fill=255)

			elif current_data['state']['flags']['cancelling']:
				# Printer paused
				display_string = "Cancelling"
				text_width = self.draw.textsize(display_string, font=self.font)[0]
				self.draw.text((self.width / 2 - text_width / 2, top + 6), display_string, font=self.font, fill=255)

			elif current_data['state']['flags']['ready'] and (current_data['progress']['completion'] or 0) < 100:
				# Printer connected, not printing
				display_string = "Waiting For Job"
				text_width = self.draw.textsize(display_string, font=self.font)[0]
				self.draw.text((self.width / 2 - text_width / 2, top + 6), display_string, font=self.font, fill=255)

			else:
				percentage = int(current_data['progress']['completion'] or 0)
				time_left = current_data['progress']['printTimeLeft'] or 0

				# Progress bar
				self.draw.rectangle((0, top + 2, self.width - 1, top + 10), fill=0, outline=255, width=1)
				bar_width = int((self.width - 5) * percentage / 100)
				self.draw.rectangle((2, top + 4, bar_width, top + 8), fill=255, outline=255, width=1)

				# Percentage and ETA
				self.draw.text((0, top + 12), "%s%%" % (percentage), font=self.font, fill=255)
				eta = time.strftime(self._eta_strftime, time.localtime(time.time() + time_left))
				eta_width = self.draw.textsize(eta, font=self.font)[0]
				self.draw.text((self.width - eta_width, top + 12), eta, font=self.font, fill=255)
		except Exception as ex:
			self.log_error(ex)

	# Taken from tpmullan/OctoPrint-DetailedProgress
	def _get_time_from_seconds(self, seconds):
		hours = 0
		minutes = 0

		if seconds >= 3600:
			hours = int(seconds / 3600)
			seconds = seconds % 3600

		if seconds >= 60:
			minutes = int(seconds / 60)
			seconds = seconds % 60

		return self._etl_format.format(**locals())

	def log_error(self, ex):
		"""
		Helper function for more complete logging on exceptions
		"""
		
		template = "An exception of type {0} occurred on {1}. Arguments: {2!r}"
		message = template.format(type(ex).__name__, inspect.currentframe().f_code.co_name, ex.args)
		self._logger.warn(message)

__plugin_name__ = "Display Panel Plugin"
__plugin_pythoncompat__ = ">=3,<4" # only python 3

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = Display_panelPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

