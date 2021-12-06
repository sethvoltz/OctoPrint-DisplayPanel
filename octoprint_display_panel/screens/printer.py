"""Printer-centric Micro Panel screens.
"""
import time
import threading
from octoprint.events import Events, eventManager
from octoprint.util import monotonic_time

from . import base

import logging
logger = logging.getLogger('octoprint.plugins.display_panel.screens.printer')


class PrinterHelper:
    """This class offers a few helpers to access commonly used data.

    It normally proxies all attribute accesses to its `_printer`
    instance variable, so for most purposes it can be treated
    equivalently to the `_printer` instance.

    """
    def __init__(self, _printer):
        self._printer = _printer

    def __getattr__(self, key):
        if self._printer:
            return getattr(self._printer, key)

    # Helper methods

    @property
    def flags(self):
        return self._printer.get_current_data()['state']['flags']

    @property
    def progress(self):
        return self._printer.get_current_data()['progress']

    @property
    def job(self):
        return self._printer.get_current_data()['job']

    def is_disconnected(self):
        if self._printer is None:
            return True
        return self._printer.get_current_connection()[0] == 'Closed'
        

def get_time_from_seconds(seconds):
    """Convert a number of seconds into a human readable duration.

    Taken from tpmullan/OctoPrint-DetailedProgress
    """
    hours = 0
    minutes = 0
    if seconds >= 3600:
        hours = seconds // 3600
        seconds %= 3600
    if seconds >= 60:
        minutes = seconds // 60
        seconds %= 60
    
    return f"{hours:02d}h {minutes:02d}m {seconds:02d}s"
    

def float_count_formatter(number, max_chars):
    """Show decimals up to length max_chars, then rounds to integer
    """

    int_part = str(int(round(number)))
    if len(int_part) >= max_chars - 1:
        return int_part
    return f"{number:0.{max_chars-len(int_part)-1}f}"


class PrinterInfoScreen(base.MicroPanelScreenBase):
    """Base Information about the printer (temperatures)
    """
    def __init__(self, width, height, _printer):
        super().__init__(width, height)
        self._printer = _printer
        
    def draw(self):
        c = self.get_canvas()
        c.text((0, 0), "Printer Temperatures")
        head_text = "no printer"
        bed_text = "no printer"
        
        if not self._printer.is_disconnected():
            temperatures = self._printer.get_current_temperatures()
            tool = temperatures.get('tool0')
            if tool:
                head_text = f"{tool['actual']} / {tool['target']}\xb0C"
            else:
                head_text = "no tool"
                
            bed = temperatures.get('bed')
            if bed:
                bed_text = f"{bed['actual']} / {bed['target']}\xb0C"
            else:
                bed_text = "no bed"
        c.text((0, 9), f'Head: {head_text}')
        c.text((0, 18), f' Bed: {bed_text}')

        return c.image

    EVENTS = [
        Events.DISCONNECTED, Events.CONNECTED, Events.CONNECTING,
        Events.CONNECTIVITY_CHANGED, Events.DISCONNECTING,
        Events.Z_CHANGE, Events.PRINTER_STATE_CHANGED
    ]

    def handle_event(self, event, payload):
        return {'DRAW'}
    

class PrintStatusScreen(base.MicroPanelScreenBase):
    """Status information about the printer and any active print job.
    """
    def __init__(self, width, height, _printer):
        super().__init__(width, height)
        self._printer = _printer
        self.display_layer_progress = {
            'current_layer': -1, 'total_layer': -1,
            'current_height': -1.0, 'total_height': -1.0
        }
        
    def draw(self):
        c = self.get_canvas()
        c.text((0, 0), f"State: {self._printer.get_state_string()}")

        if self._printer.job['file']['name']:
            c.text((0, 9), f"File: {self._printer.job['file']['name']}")
            
            print_time = get_time_from_seconds(
                self._printer.progress['printTime'] or 0)
            c.text((0, 18), f"Time: {print_time}")

            # logger.info(self._printer.job) - for debugging
            if self._printer.job['filament'] is not None:
                filament = (self._printer.job['filament']['tool0']
                            if 'tool0' in self._printer.job['filament']
                            else self._printer.job['filament'])
                filament_length = float_count_formatter(
                    (filament['length'] or 0) / 1000, 3)
                filament_mass = float_count_formatter(
                    (filament['volume'] or 0), 3)
                c.text((0, 27), f"Filament: {filament_length}m/{filament_mass}cm3")

            # Display height if information available from DisplayLayerProgress
            height = (f"{self.display_layer_progress['current_height']:>5.1f}"
                      f"/{self.display_layer_progress['total_height']:>5.1f}")
            if self.display_layer_progress['total_layer'] != -1.0:          
                layer = (f"{self.display_layer_progress['current_layer']:4d}"
                         f"/{self.display_layer_progress['total_layer']:4d}")
            else:
                layer = (f"{self.display_layer_progress['current_layer']:4d}")
           
            height_text = ""
            if (self.display_layer_progress['current_height'] != -1.0
                and self.display_layer_progress['current_layer'] != -1):
                height_text = f"{layer};{height}"
            elif self.display_layer_progress['current_layer'] != -1:
                height_text = layer
            elif self.display_layer_progress['current_height'] != -1.0:
                height_text = height
            if height_text:
                c.text((0, 36), height_text)
            
        else:
            c.text((0, 18), "Waiting for file...")

        return c.image
            
    EVENTS = [
        Events.DISCONNECTED, Events.CONNECTED, Events.CONNECTING,
        Events.CONNECTIVITY_CHANGED, Events.DISCONNECTING,
        Events.Z_CHANGE, Events.PRINTER_STATE_CHANGED, Events.PRINT_FAILED,
        Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_CANCELLING,
        Events.PRINT_PAUSED, Events.PRINT_RESUMED,
        "DisplayLayerProgress_heightChanged",
        "DisplayLayerProgress_layerChanged"
    ]

    def handle_event(self, event, payload):
        if event in (Events.PRINT_FAILED, Events.PRINT_DONE,
                     Events.PRINT_CANCELLED, Events.PRINT_CANCELLING):
            self.display_layer_progress = {
                'current_height': -1.0, 'current_layer': -1,
                'total_height': -1.0, 'total_layer': -1
            }
        elif event in ("DisplayLayerProgress_heightChanged",
                       "DisplayLayerProgress_layerChanged"):
            self.display_layer_progress = {
                'current_height': (float(payload.get('currentHeight'))
                                   if payload.get('currentHeight') != "-"
                                   else -1.0),
                'current_layer': (int(payload.get('currentLayer'))
                                  if payload.get('currentLayer') != "-"
                                  else -1),
                'total_height': (float(payload.get('totalHeight'))
                                 if payload.get('totalHeight') != "-"
                                 else -1.0),
                'total_layer': (int(payload.get('totalLayer'))
                                if payload.get('totalLayer') != "-" 
                                else -1)
            }
            
        return {'DRAW'}

    
class PrinterStatusBarScreen(base.MicroPanelScreenBase):
    """The common status bar, showing either printer state or job progress.
    """
    def __init__(self, width, height, _printer, _settings):
        super().__init__(width, height)
        self._printer = _printer
        self._settings = _settings
        
    def draw(self):
        c = self.get_canvas()
        display_string = ""
        if self._printer.is_disconnected():
            display_string = "Printer Not Connected"
        elif self._printer.flags['paused'] or self._printer.flags['pausing']:
            display_string = "Paused"
        elif self._printer.flags['cancelling']:
            display_string = "Cancelling"
        elif (self._printer.flags['ready']
              and (self._printer.progress['completion'] or 0) < 100):
            if self._printer.job['file']['name']:
                display_string = "Ready to Start"
            else:
                display_string = "Waiting for Job"
        elif self._printer.is_printing():
            display_string = ""  # draw progress bar while printing
        else:
            display_string = self._printer.get_state_string()
            display_string = display_string.replace("connection", "conn")

        if display_string:
            c.text_centered(4, display_string)
            return c.image
        
        ###
        ### Draw the progress bar
        ###
        
        percentage = self._printer.progress['completion'] or 0
        print_time = self._printer.progress['printTime'] or 0
        time_left = self._printer.progress['printTimeLeft'] or 0

        # Calculate progress from time
        if self._settings.get_boolean(['timebased_progress']) and print_time:
            percentage = (print_time * 100) / (print_time + time_left)

        # Progress bar
        c.rectangle((0, 0, self.width - 1, 5), fill=0, outline=255, width=1)
        bar_width = int((self.width - 5) * (percentage / 100))
        c.rectangle((2, 2, bar_width, 3), fill=255, outline=255, width=1)

        # Percentage and ETA
        c.text((0, 5), f"{percentage:.0f}%")
        eta = time.strftime(self._settings.get(["eta_strftime"], merged=True),
                            time.localtime(time.time() + time_left))
        c.text_right(5, eta)

        return c.image

    EVENTS = [
        Events.DISCONNECTED, Events.CONNECTED, Events.CONNECTING,
        Events.CONNECTIVITY_CHANGED, Events.DISCONNECTING,
        Events.Z_CHANGE, Events.PRINTER_STATE_CHANGED, Events.PRINT_FAILED,
        Events.PRINT_DONE, Events.PRINT_CANCELLED, Events.PRINT_CANCELLING,
        Events.PRINT_PAUSED, Events.PRINT_RESUMED,
    ]

    def handle_event(self, event, payload):
        return {'DRAW'}
    

class JobCancelScreen(base.MicroPanelScreenBase):
    """The job cancel screen.
    
    This screen is shown by the MicroPanelScreenTop when the cancel
    button is pressed.

    """
    def __init__(self, width, height, _printer):
        super().__init__(width, height)
        self._printer = _printer
        self.press_time = monotonic_time()
        self.expired = False
        self.timer = threading.Timer(10, self.timer_expired)
        self.timer.start()
        
    def draw(self):
        c = self.get_canvas()
        c.text_centered(0, ("Cancel Print?\n"
                            "Press 'X' to confirm\n"
                            "Press any button or\n"
                            "wait 10 sec to escape"))
        return c.image

    def handle_button(self, label):
        if label == 'cancel':
            if self.expired or (monotonic_time() - self.press_time) < 1.0:
                return {'IGNORE'}
            
            self._printer.cancel_print()

        self.expired = True
        return {'BACK'}

    # A synthetic event, defined below, is fired when the 10 second
    # timer expires. This event is needed in order to make the plugin
    # core aware that the screen needs to be redrawn.
    
    EXPIRED_EVENT = 'MicroPanel_JobCancelScreenExpired'
        
    def timer_expired(self):
        if not self.expired:
            # disable button, just in case there's a last minute race
            self.expired = True
            # send an event to myself
            eventManager().fire(self.EXPIRED_EVENT)
        
    EVENTS = [EXPIRED_EVENT]
    
    def handle_event(self, event, payload):
        if event == self.EXPIRED_EVENT:
            return {'BACK'}
