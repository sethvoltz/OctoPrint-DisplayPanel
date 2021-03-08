
from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT = ImageFont.load_default()


class MicroPanelCanvas:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def fill(self, color):
        self.rectangle((0, 0, self.width, self.height), fill=color)

    def text(self, point, message, **kwargs):
        kwargs.setdefault('font', DEFAULT_FONT)
        kwargs.setdefault('fill', 255)
        self.draw.text(point, message, **kwargs)

    def text_right(self, y, message, **kwargs):
        kwargs.setdefault('font', DEFAULT_FONT)
        text_size = self.textsize(message, font=kwargs['font'])
        if '\n' in message:
            lines = message.rstrip('\n').split('\n')
            line_height = text_size[1] / len(lines)
            for i, line in enumerate(message.rstrip('\n').split('\n')):
                self.text_right(y + (i * line_height), line, **kwargs)
        else:
            x = self.width - text_size[0]
            self.text((x, y), message, **kwargs)
        
    def text_centered(self, y, message, **kwargs):
        kwargs.setdefault('font', DEFAULT_FONT)
        text_size = self.textsize(message, font=kwargs['font'])
        if '\n' in message:
            lines = message.rstrip('\n').split('\n')
            line_height = text_size[1] / len(lines)
            for i, line in enumerate(message.rstrip('\n').split('\n')):
                self.text_centered(y + (i * line_height), line, **kwargs)
        else:
            x = (self.width / 2) - (text_size[0] / 2)
            self.text((x, y), message, **kwargs)
        
    def __getattr__(self, key):
        return getattr(self.draw, key)


class MicroPanelScreenBase:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.subscreen = None

    def draw(self):
        """Create an image representing the current state of this screen.
        """
        # TODO: add separate functions for drawing the main body
        #       full-screen, for drawing the body accounting for a
        #       header, and for drawing the header. The top level
        #       plugin will decide which functions it wants to call.
        pass

    def handle_button(self, label):
        """Take action on the given button press.

        This function may return a set containing action flags:
        - 'BACK': The current subscreen should be removed
        - 'DRAW': The screen should be refreshed
        - 'IGNORE': The button press should not be handled by a parent screen

        """
        pass

    EVENTS = []
    
    def wants_event(self, event):
        """True if this event is in the list of events processed by this screen.
        """
        return event in self.EVENTS
    
    def handle_event(self, event, payload):
        """Take action on the given OctoPrint event.

        This function may return a set containing action flags:
        - 'BACK': The current subscreen should be removed
        - 'DRAW': The screen should be refreshed
        - 'IGNORE': The event should not be handled by a parent screen

        """
        pass

    def set_subscreen(self, screen):
        """Set the given screen as an active subscreen of this one.

        All draw and event handling will be processed by the subscreen
        until either something removes the subscreen here or the event
        or button handlers return a value 'BACK'.

        """
        self.subscreen = screen
        
    @property
    def image(self):
        if self.subscreen is not None:
            img = self.subscreen.image
            if img:
                return img
        return self.draw()
        
    def process_event(self, event, payload):
        r = set()
        if self.subscreen is not None:
            if self.subscreen.wants_event(event):
                r.update(self.subscreen.process_event(event, payload))

        if 'BACK' in r:
            self.subscreen = None
            r.remove('BACK')
            r.add('DRAW')
                
        if self.wants_event(event):
            r.update(self.handle_event(event, payload) or set())

        return r

    def process_button(self, label):
        r = set()
        if self.subscreen is not None:
            r.update(self.subscreen.process_button(label))

        if 'BACK' in r:
            self.subscreen = None
            r.remove('BACK')
            r.add('DRAW')
        elif not r:
            r.update(self.handle_button(label) or set())
            
        return r

    def get_canvas(self):
        return MicroPanelCanvas(self.width, self.height)
