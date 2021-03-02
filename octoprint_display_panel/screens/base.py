

class MicroPanelScreenBase:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self._subscreen = None
        
    def draw(self):
        """Create an image representing the current state of this screen.
        """
        # TODO: add separate functions for drawing the main body
        #       full-screen, for drawing the body accounting for a
        #       header, and for drawing the header. The top level
        #       plugin will decide which functions it wants to call.
        
        # TODO: If a subscreen does not return a value for a drawing
        #       function, the parent screen should return its value.
        pass

    def handle_button(self, label):
        """Take action on the given button press.
        """
        # TODO: return value should be a set with flags in it, such as
        #       'BACK' (the user or event wants to return up to the
        #       parent screen) or 'DRAW' (the event requires a screen
        #       refresh)
        pass

    EVENTS = []
    
    def wants_event(self, event):
        """True if this event is in the list of events processed by this screen.
        """
        return event in self.EVENTS
    
    def handle_event(self, event, payload):
        """Take action on the given OctoPrint event.
        """
        pass

    def set_subscreen(self, screen, *args, **kwargs):
        """Set the given screen as an active subscreen of this one.

        All draw and event handling will be processed by the subscreen
        until either something removes the subscreen here or the event
        or button handlers return a value 'BACK'.

        """
        self.subscreen = screen(self.width, self.height, *args, **kwargs)
        
