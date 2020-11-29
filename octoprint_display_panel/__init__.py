# coding=utf-8
from __future__ import absolute_import

# system stats 
import psutil
import shutil
import socket

import random

import octoprint.plugin
from octoprint.util import RepeatedTimer
import time
import subprocess
from enum import Enum
from board import SCL, SDA
import busio
from PIL import Image, ImageDraw, ImageFont
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

	print_complete = False
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

	##~~ StartupPlugin mixin

	def on_after_startup(self):
		self.setup_gpio()
		self.configure_gpio()
		self.clear_display()
		self.check_system_stats()
		self.start_system_timer()
		self.print_complete = False
		self.screen_mode = ScreenMode.SYSTEM
		self.update_ui()

	##~~ ShutdownPlugin mixin

	def on_shutdown(self):
		self.clear_display()

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		self._logger.info("on_event: %s", event)

	##~~ ProgressPlugin mixin

	def on_print_progress(self, storage, path, progress):
		self._logger.info("on_print_progress: %s", progress)

	def on_slicing_progress(self, slicer, source_location, source_path, destination_location, destination_path, progress):
		self._logger.info("on_slicing_progress: %s", progress)

	##~~ Softwareupdate hook

	def get_update_information(self):
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
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("8.8.8.8", 80))
		self.system_stats['ip'] = s.getsockname()[0]
		s.close()
		self.system_stats['load'] = psutil.getloadavg()
		self.system_stats['memory'] = psutil.virtual_memory()
		self.system_stats['disk'] = shutil.disk_usage('/') # disk percentage = 100 * used / (used + free)

		if self.screen_mode == ScreenMode.SYSTEM:
			self.update_ui()

	def setup_gpio(self):
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
		try:
			for gpio_pin in self.input_pinset:
				GPIO.setup(gpio_pin, GPIO.IN, GPIO.PUD_UP)
				GPIO.remove_event_detect(gpio_pin)
				self._logger.info("Adding GPIO event detect on pin %s with edge: RISING", gpio_pin)
				GPIO.add_event_detect(gpio_pin, GPIO.RISING, callback=self.handle_gpio_event, bouncetime=200)
		except Exception as ex:
			self.log_error(ex)

	def handle_gpio_event(self, channel):
		try:
			if channel in self.input_pinset:
				label = self.input_pinset[channel]
				self._logger.info("GPIO Button triggered on %s for %s", channel, label)
				if label == 'mode':
					self.next_mode()
		except Exception as ex:
			self.log_error(ex)
			pass

	def next_mode(self):
		self.screen_mode = self.screen_mode.next()
		self._logger.info("Setting mode to %s", self.screen_mode)
		self.update_ui()

	def clear_display(self):
		self.disp.fill(0)
		self.disp.show()

	def update_ui(self):
		if self.screen_mode == ScreenMode.SYSTEM:
			self.update_ui_system()
		elif self.screen_mode == ScreenMode.PRINTER:
			self._logger.info("DRAW Screen Mode PRINTER")
			self.update_ui_printer()
		elif self.screen_mode == ScreenMode.PRINT:
			self._logger.info("DRAW Screen Mode PRINT")
			self.update_ui_print()
		
		self.update_ui_bottom()

		# Display image.
		self.disp.image(self.image)
		self.disp.show()
	
	def update_ui_system(self):
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		# Draw a black filled box to clear the image.
		self.draw.rectangle((0, 0, self.width, bottom), fill=0)

		mem = self.system_stats['memory']
		disk = self.system_stats['disk']
		# Write four lines of text.
		self.draw.text((left, top + 0), "IP: %s" % (self.system_stats['ip']), font=self.font, fill=255)
		self.draw.text((left, top + 9), "Load: %s, %s, %s" % self.system_stats['load'], font=self.font, fill=255)
		self.draw.text((left, top + 18), "Mem: %s/%s MB %s%%" % (int(mem.used/1048576), int(mem.total/1048576), mem.percent), font=self.font, fill=255)
		self.draw.text((left, top + 27), "Disk: %s/%s GB %s%%" % (int(disk.used/1073741824), int((disk.used+disk.total)/1073741824), int(10000*disk.used/(disk.used+disk.free))/100), font=self.font, fill=255)

	def update_ui_printer(self):
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		self.draw.rectangle((0, 0, self.width, bottom), fill=0)
		self.draw.text((left, top + 9), "Mode: Printer", font=self.font, fill=255)

	def update_ui_print(self):
		top = 0
		bottom = self.height - self.bottom_height
		left = 0

		self.draw.rectangle((0, 0, self.width, bottom), fill=0)
		self.draw.text((left, top + 9), "Mode: Print", font=self.font, fill=255)
	
	def update_ui_bottom(self):
		top = self.height - self.bottom_height
		bottom = self.height
		left = 0

		self.draw.rectangle((0, top, self.width, bottom), fill=0)
		self.draw.rectangle((0, top + 2, self.width - 1, top + 10), fill=0, outline=255, width=1)
		percentage = random.random()
		bar_width = int((self.width - 5) * percentage)
		self.draw.rectangle((2, top + 4, bar_width, top + 8), fill=255, outline=255, width=1)
		self.draw.text((0, top + 12), "%s%%" % (int(percentage * 100)), font=self.font, fill=255)
		finish_wall_time = "12:34"
		self.draw.text((self.width - self.draw.textsize(finish_wall_time, font=self.font)[0], top + 12), finish_wall_time, font=self.font, fill=255)

	def log_error(self, ex):
		template = "An exception of type {0} occurred on {1}. Arguments:\n{2!r}"
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

