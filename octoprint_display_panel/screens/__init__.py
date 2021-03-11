"""Top-level implementation of Micro Panel screens.

Each screen consists of a set of data that can be shown to the user,
can be updated through events from OctoPrint's main event system, and
can react to user interaction through button presses. Screens must
implement the `draw()` method at a minimum, but can implement
`handle_button()` and/or `handle_event()` as well. Screens may also
designate another screen instance as a "subscreen", which will
temporarily replace the contents of the screen. For more details about
implementing screens, see base.py.

"""
from octoprint.events import Events

from . import base, system, printer, soft_buttons


class MessageScreen(base.MicroPanelScreenBase):
    """A trivial implementation of a screen, for displaying a simple message.

    This screen is used by the main __init__.py as a fallback display
    in case the main set of screens cannot be initialized.

    """
    def __init__(self, width, height, message):
        super().__init__(width, height)
        self.message = message

    def draw(self):
        c = self.get_canvas()
        c.text_centered(0, self.message)
        return c.image


class MicroPanelScreenTop(base.MicroPanelScreenBase):
    """The top-level screen for the Micro Panel.

    This class uses extensive overrides of the base class in order to
    implement its core behavior, which is to support a small status
    bar screen as well as a rotating subscreen. Most typical screens
    will not need this level of complexity.

    """
    def __init__(self, width, height, _printer, _settings, _file_manager):
        self._printer = printer.PrinterHelper(_printer)
        self._settings = _settings
        self._file_manager = _file_manager

        # Define the status bar screen, which is typically displayed.
        self.status_bar_height = 16
        if self._settings.get_boolean(["progress_on_top"], merged=True):
            self.status_bar_top = 0
        else:
            self.status_bar_top = height - self.status_bar_height
        self.status_bar_screen = printer.PrinterStatusBarScreen(
            width, self.status_bar_height, self._printer, self._settings)

        # Define the main set of subscreens. These screens will be
        # rotated through via the 'mode' button in the order they are
        # listed below.
        self.subscreen_height = height - self.status_bar_height
        self.screens = {
            'system': system.SystemInfoScreen(width, self.subscreen_height),
            'printer': printer.PrinterInfoScreen(width, self.subscreen_height,
                                                 self._printer),
            'print': printer.PrintStatusScreen(width, self.subscreen_height,
                                               self._printer),
            'softbuttons': soft_buttons.SoftButtonsScreen(
                width, self.subscreen_height, self._printer, self._settings),
            'fileselect': soft_buttons.FileSelectScreen(
                width, self.subscreen_height, self._printer,
                self._file_manager, self._settings),
        }
        self.current_screen = 'system'
        self.set_subscreen(self.current_screen)
        super().__init__(width, height)

    # This use of a property setter overrides the base behavior of
    # subscreens, so that if the subscreen is being set to None, it
    # instead gets set to the value of self.current_screen.
    @property
    def subscreen(self):
        return self.__subscreen

    @subscreen.setter
    def subscreen(self, s):
        if s is None:
            self.set_subscreen(getattr(self, 'current_screen', None))
        else:
            self.__subscreen = s
        
    def set_subscreen(self, screen):
        """Set the desired subscreen, via string or subscreen instance.
        """
        if isinstance(screen, str):
            self.current_screen = screen
            screen = self.screens[screen]
        super().set_subscreen(screen)

    def next_subscreen(self):
        """Rotate to the next subscreen in the set of screens.
        """
        screen_list = list(self.screens.keys())
        i = screen_list.index(self.current_screen)
        i = (i + 1) % len(screen_list)
        self.set_subscreen(screen_list[i])
        
    @property
    def image(self):
        """Render this screen by combining the status bar and the subscreen.
        """
        if self.status_bar_top == 0:
            main_top = self.status_bar_height
        else:
            main_top = 0
            
        c = self.get_canvas()
        main_image = super().image
        c.image.paste(main_image, (0, main_top))
        if main_image.size[1] < self.height:
            c.image.paste(self.status_bar_screen.image,
                          (0, self.status_bar_top))
        return c.image

    def handle_button(self, label):
        """Take action on a button press, if not handled by the subscreen.
        """
        if label == 'mode':
            self.next_subscreen()
            return {'DRAW'}

        if label == 'play':
            if self._printer.is_disconnected():
                if self._printer:
                    self._printer.connect()
                return {'DRAW'}

            if (self._printer.flags['ready']
                and (self._printer.progress['completion'] or 0) == 0
                and self._printer.job['file']['name']):
                self._printer.start_print()
                return {'DRAW'}

            if not self._printer.is_paused():
                return {'IGNORE'}

            self._printer.resume_print()
            return {'DRAW'}
            
        if label == 'pause':
            if not self._printer or not self._printer.is_printing():
                return {'IGNORE'}

            self._printer.pause_print()
            return {'DRAW'}

        if label == 'cancel':
            if self._printer.is_disconnected():
                return {'IGNORE'}

            if (not self._printer.is_printing()
                and not self._printer.is_paused()):
                return {'IGNORE'}
            
            self.set_subscreen(
                printer.JobCancelScreen(self.width, self.subscreen_height,
                                        self._printer))
            return {'DRAW'}

    # The list of events to be processed by this screen
    EVENTS = [
        Events.DISCONNECTED, Events.PRINT_STARTED
    ]

    def handle_event(self, event, payload):
        """Handle events for this screen.
        """
        # We only need to process events here that affect which
        # subscreen we are currently displaying. Events affecting the
        # display of subscreens will be automatically passed to the
        # subscreen.
        if event == Events.DISCONNECTED:
            self.set_subscreen('system')
        elif event == Events.PRINT_STARTED:
            self.set_subscreen('print')

        return {'DRAW'}

    def process_event(self, event, payload):
        """Distribute all incoming events.

        This method is overridden in order to pass events to the
        status bar as well as to the print status screen when it is
        not being displayed.

        """
        r = set()
        # also pass the event to the status bar screen
        if self.status_bar_screen.wants_event(event):
            r.update(self.status_bar_screen.process_event(event, payload))

        # and pass it to certain subscreens, if it isn't being displayed
        for screen in ('print', 'fileselect', 'softbuttons'):
            if self.screens[screen].wants_event(event):
                if self.subscreen != self.screens[screen]:
                    # don't propagate its response, because it's not on screen
                    self.screens[screen].process_event(event, payload)
            
        r.update(super().process_event(event, payload))
        return r
