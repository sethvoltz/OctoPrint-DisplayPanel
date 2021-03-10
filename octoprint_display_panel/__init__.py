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
from PIL import Image, ImageDraw, ImageFont
import inspect

from . import panels
from .panels.virtual_panel import VirtualPanelMixin


from . import screens


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
                          octoprint.plugin.SettingsPlugin,
                          VirtualPanelMixin):

	_display_init = False
	_etl_format = "{hours:02d}h {minutes:02d}m {seconds:02d}s"
	_eta_strftime = ""
	_image_rotate = False
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
		self.clear_display()
		self.check_system_stats()
		self.start_system_timer()
		self.update_ui()

	##~~ ShutdownPlugin mixin

	def on_shutdown(self):
		"""
		ShutdownPlugin lifecycle hook, called before Octoprint shuts down
		"""

		self.clear_display()
		self.shutdown_display()

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		"""
		EventHandlerPlugin lifecycle hook, called whenever an event is fired
		"""

		self._logger.info("on_event: %s", event)

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

		c = [dict(type="settings", custom_bindings=False)]
		if self._settings.get_boolean(['virtual_panel'], merged=True):
			c.append(dict(type="tab", name="Micro Panel", template="display_panel_virtualpanel.jinja2", custom_bindings=False))
		return c

	##~~ SettingsPlugin mixin

	def initialize(self):
		"""
		Prepare variables for setting modification detection
		"""

		self._display_init = False
		self._eta_strftime = str(self._settings.get(["eta_strftime"]))
		self._image_rotate = bool(self._settings.get(["image_rotate"]))
		self._progress_on_top = bool(self._settings.get(["progress_on_top"]))
		self._screen_mode = ScreenModes.SYSTEM
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
			virtual_panel = False, # Default is disabled
		)

	def on_settings_save(self, data):
		"""
		SettingsPlugin lifecycle hook, called when settings are saved
		"""
		previous = self._settings.get_all_data()
                
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		# update the display when any setting changes
		if self._settings.get_all_data() != previous:
			self.clear_display()
			self.setup_display()
			self.clear_display()
			self.check_system_stats()
			self.start_system_timer()
			self._screen_mode = ScreenModes.SYSTEM
			self.update_ui()
		

	##~~ Helpers

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
			if self._display_init:
				self.disp.setup(self._settings)
			else:
				self.disp = panels.Panels(
					self._settings,
					self.handle_button_press
				)
				
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

	def shutdown_display(self):
		"""Shut down display panels.
		"""
		self.disp.shutdown()

	def setup_screens(self):
		"""Create the top level screen.
		"""
		self._logger.info("Initializing screens...")
		try:
		        self.top_screen = screens.MicroPanelScreenTop(
				self.width, self.height,
				self._printer, self._settings,
				self._file_manager
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

			self.disp.update_timer(self._printer_state)

	def start_display_timer(self, reconfigure=False):
		# Vestigial, should be deleted
		pass

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

__plugin_name__ = "OctoPrint Micro Panel"
__plugin_pythoncompat__ = ">=3,<4" # only python 3

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = Display_panelPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

