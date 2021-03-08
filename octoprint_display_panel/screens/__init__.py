
from . import base, system, printer


class MicroPanelScreenTop(base.MicroPanelScreenBase):
    def __init__(self, width, height, _printer, _settings):
        super().__init__(width, height)
        self._printer = printer.PrinterHelper(_printer)
        self._settings = _settings

        self.status_bar_height = 16
        if status_bar_on_top:
            self.status_bar_top = 0
        else:
            self.status_bar_top = height - self.status_bar_height
        self.status_bar_screen = printer.PrinterStatusBarScreen(
            width, self.status_bar_height, self._printer, self._settings)

        self.subscreen_height = height - self.status_bar_height
        self.screens = {
            'system': system.SystemInfoScreen(width, self.subscreen_height),
            'printer': printer.PrinterInfoScreen(width, self.subscreen_height,
                                                 self._printer),
            'print': printer.PrintStatusScreen(width, self.subscreen_height,
                                               self._printer),
        }
        self.current_screen = 'system'
        self.set_subscreen(self.current_screen)

    # This use of a property setter overrides the base behavior of
    # subscreens, so that if the subscreen is being set to None, it
    # instead gets set to the value of self.current_screen.
    @property
    def subscreen(self):
        return self.__subscreen

    @subscreen.setter
    def subscreen(self, s):
        if s is None:
            self.set_subscreen(self.current_screen)
        else:
            self.__subscreen = s
        
    def set_subscreen(self, screen):
        if isinstance(screen, str):
            screen = self.screens[screen]
            self.current_screen = screen
        size = (self.width, self.height - self.status_bar_height)
        super().set_subscreen(screen, size=size)

    def next_subscreen(self):
        screen_list = list(self.screens.keys())
        i = screen_list.index(self.current_screen)
        i = (i + 1) % len(screen_list)
        self.set_subscreen(screen_list[i])
        
    @property
    def image(self):
        if self.status_bar_top == 0:
            main_top = self.status_bar_height
        else:
            main_top = 0
            
        c = self.get_canvas()
        main_image = super().image
        c.image.paste(main_image, (0, main_top))
        if main_image.size[1] < self.height:
            c.image.paste(self.status_bar_screen.image, (0, status_bar_top))
        return c.image

    def handle_button(self, label):
        if label == 'menu':
            self.next_subscreen()
            return {'DRAW'}

        if label == 'play':
            if printer.PRINTER.is_disconnected:
                if printer.PRINTER:
                    printer.PRINTER.connect()
                return {'DRAW'}

            if (printer.PRINTER.flags['ready']
                and (printer.PRINTER.progress['completion'] or 0) == 0
                and printer.PRINTER.job['file']['name']):
                printer.PRINTER.start_print()
                return {'DRAW'}

            if not printer.PRINTER.is_paused():
                return {'IGNORE'}

            printer.PRINTER.resume_print()
            return {'DRAW'}
            
        if label == 'pause':
            if not printer.PRINTER or not printer.PRINTER.is_printing():
                return {'IGNORE'}

            printer.PRINTER.pause_print()
            return {'DRAW'}

        if label == 'cancel':
            if printer.PRINTER.is_disconnected:
                return {'IGNORE'}

            if (not printer.PRINTER.is_printing()
                and not printer.PRINTER.is_paused()):
                return {'IGNORE'}
            
            self.set_subscreen(
                printer.JobCancelScreen(self.width, self.subscreen_height))
            return {'DRAW'}

    EVENTS = [
        Events.DISCONNECTED, Events.PRINT_STARTED
    ]

    def handle_event(self, event, payload):
        if event == Events.DISCONNECTED:
            self.set_subscreen('system')
        elif event == Events.PRINT_STARTED:
            self.set_subscreen('print')

        return {'DRAW'}
