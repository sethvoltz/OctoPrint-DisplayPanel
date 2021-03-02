

from . import base, system, printer

class MicroPanelScreenTop(base.MicroPanelScreenBase):
    def __init__(self, width, height):
        super().__init__(width, height)

        self.screens = [
            system.SystemInfoScreen,
            printer.PrinterInfoScreen,
            printer.PrintStatusScreen,
        ]
        self.current_screen = 0
        self.set_subscreen(self.screens[0])

    def handle_button(self, label):
        if label == 'menu':
            self.current_screen += 1
            self.current_screen %= len(self.screens)
            self.set_subscreen(self.screens[0])
            return {'DRAW'}
        else:
            return MicroPanelScreenBase.handle_button(self, label)
        
#    def draw(self):
#        return self.screens[self.current_screen].draw()
#
#    def wants_event(self, event):
#        return True
#    
#    def handle_event(self, event, payload):
#        retval = {}
#        for screen in self.screens:
#            if screen.wants_event(event):
#                v = screen.handle_event(event, payload)
#                if v is not None:
#                    retval.add(v)
#        return retval
