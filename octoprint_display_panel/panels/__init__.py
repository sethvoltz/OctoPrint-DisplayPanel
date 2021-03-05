from octoprint.util import ResettableTimer

try:
    from . import micro_panel
except (NotImplementedError, ImportError):
    micro_panel = None

from . import virtual_panel

import logging
logger = logging.getLogger("octoprint.plugins.display_panel.virtual_panel")


class DisplayTimer:
    """Coordination class for display timeout.
    """
    def __init__(self, settings, panel):
        self.panel = panel
        self.timer = None
        self.blank = False
        self.last_printer_state = 4
        self.setup(settings)

    def setup(self, settings):
        """Adjust settings when changed by the user.
        """
        self.timeout = settings.get_int(['display_timeout_time'], merged=True)
        self.mode = settings.get_int(['display_timeout_option'], merged=True)
        self.cancel()
        self.update(self.last_printer_state)

    def cancel(self):
        """Cancel the running timer.
        """
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def update(self, printer_state):
        """Activate or deactivate the timer depending on the printer state.
        
        If the printer_state is less than or equal to the
        'display_timeout_option' setting, then the timer is active and
        the display may shutdown. While the printer_state is greater
        than the 'display_timeout_option' setting, the display will
        not shut down.

        """
        self.last_printer_state = printer_state
        if printer_state <= self.mode:
            if not self.timer:
                self.timer = ResettableTimer(self.timeout * 60,
                                             self.sleep, daemon=True)
                self.timer.start()
        else:
            self.cancel()
            if self.blank:
                self.wake()

    def sleep(self):
        """Put the display to sleep and deactivate the timer.
        """
        self.blank = True
        self.panel.poweroff()
        self.cancel()

    def wake(self):
        """Activate the display and restore the timer based on the last
        known printer state.
        """
        self.blank = False
        self.panel.poweron()
        self.update(self.last_printer_state)

    def poke(self):
        """Reset the timer's timeout.

        Typically called as part of a button press handler.
        """
        if self.timer:
            self.timer.reset()
        
    @property
    def is_blank(self):
        return self.blank

    
class Panels:
    """Proxy class for one or more panels that have a screen and buttons.
    """
    # These are default values in case the MicroPanel is not
    # initialized. The VirtualPanel will always have the same
    # dimensions as the MicroPanel (or any other variant of a hardware
    # panel).
    width = 128
    height = 64

    def __init__(self, settings, button_callback):
        self.button_callback = button_callback
        self.display_timer = DisplayTimer(settings, self)
        self.panels = []
        
        # Only try to connect to the micro panel if it successfully
        # was able to be imported
        if micro_panel is not None:
            panel = micro_panel.MicroPanel(self.handle_button)
            panel.setup(settings)
            self.width, self.height = panel.width, panel.height
            self.panels.append(panel)

        # TODO: make the virtual panel dependent on a setting
        if True:
            panel = virtual_panel.VirtualPanel(self.width, self.height,
                                               self.handle_button)
            self.panels.append(panel)

    def setup(self, settings):
        """Apply the provided settings to all panels in this collection.
        """
        self.display_timer.setup(settings)
        for panel in self.panels:
            if hasattr(panel, 'setup'):
                panel.setup(settings)

    def handle_button(self, label):
        """Intercept button press events in order to either wake or poke
        the display timer.
        """
        if self.display_timer.is_blank:
            # ignore this press, instead it's being used to wake the display
            self.display_timer.wake()
        else:
            self.display_timer.poke()
            self.button_callback(label)

    def update_timer(self, printer_state):
        """Pass printer state information to the display timer.
        """
        self.display_timer.update(printer_state)
                
    def __getattr__(self, key):
        """Proxy method calls to child panels.

        Methods that are proxied are listed in proxy_methods.
        """
        proxy_methods = ('shutdown', 'fill', 'show', 'poweroff', 'poweron',
                         'image')
        if key not in proxy_methods:
            raise AttributeError(f'attribute {key} not found')

        def proxy(*args, **kwargs):
            for panel in self.panels:
                getattr(panel, key)(*args, **kwargs)
        return proxy
