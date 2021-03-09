"""Base class of all Micro Panel screens.

The MicroPanelScreenBase class here should be subclassed to implement
your desired screen. At a minimum, you should implement the `draw()`
method:

  class HelloWorldScreen(base.MicroPanelScreenBase):
      def draw(self):
          c = self.get_canvas()
          c.text_centered(0, "Hello World!")
          return c.image

Note the use of `get_canvas()`, which returns an instance of
MicroPanelCanvas which can make certain routine drawing operations
(primarily text) easier.

Screens are drawn whenever the plugin core determines they need to be
drawn; typically, no less frequently than every 5 seconds, but can be
arbitrarily often. If your screen's data changes based on printer
events, for example, you should implement the `handle_event()` method
and the `EVENTS` list, and return a set including the string 'DRAW' to
signal that your screen is ready to be redrawn.

  class EventScreen(base.MicroPanelScreenBase):
      def __init__(self, *args, **kwargs):
          super().__init__(*args, **kwargs)
          self.last_event = "none"

      def draw(self):
          c = self.get_canvas()
          c.text((0,0), "Last Event:")
          c.text((20,10), self.last_event)
          return c.image

      EVENTS = [Events.DISCONNECTED, Events.CONNECTING, Events.CONNECTED]

      def handle_event(self, event, payload):
          self.last_event = event
          return {'DRAW'}

Similarly, if your screen needs to react to a button press, you should
implement the `handle_button()` method.

    class ButtonScreen(base.MicroPanelScreenBase):
      def __init__(self, *args, **kwargs):
          super().__init__(*args, **kwargs)
          self.last_button = "none"

      def draw(self):
          c = self.get_canvas()
          c.text((0,0), "Last Button:")
          c.text((20,10), self.last_button)
          return c.image

      def handle_button(self, label):
          self.last_button = label
          return {'DRAW'}

If `handle_button()` does not return anything or returns an empty set,
the button will be handled by the parent screen. If you want your
subscreen to not react to a certain button label, return the value
{'IGNORE'}.

You can also set a subscreen using the `set_subscreen()`
method. Subscreens will stay active until they return the value
{'BACK'} from either `handle_button()` or `handle_event()`.

"""

from PIL import Image, ImageDraw, ImageFont


DEFAULT_FONT = ImageFont.load_default()
DEFAULT_FONT_LINE_HEIGHT = 9


class MicroPanelCanvas:
    """Helper class for providing a pre-initialized drawing surface for screens.
    
    This class provides a bit of assistance with drawing text
    (particularly centered or right-aligned). It also proxies all
    other methods available from the ImageDraw.Draw class. Drawn image
    data can be retrieved by the `image` instance variable.

    """
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def fill(self, color):
        """Fill the entire canvas with the specified color.
        
        Typical colors: 0=black, 255=white

        """
        self.rectangle((0, 0, self.width, self.height), fill=color)

    def text(self, point, message, **kwargs):
        """Draw text at a point on the canvas.

        The point is a 2-tuple (x, y). It defaults to white color and
        the default font, but these and all other settings from
        `draw.text()` can be overridden with kwargs.

        """
        kwargs.setdefault('font', DEFAULT_FONT)
        kwargs.setdefault('fill', 255)
        self.draw.text(point, message, **kwargs)

    def text_right(self, y, message, **kwargs):
        """Draw text, right aligned, at the given position on the canvas.
        
        The text will be aligned to the far right edge of the canvas,
        with the top edge at the provided `y` position. If multiple
        lines are present in the message (newline separated), each
        line will be individually right aligned.

        """
        kwargs.setdefault('font', DEFAULT_FONT)
        text_size = self.textsize(message, font=kwargs['font'])
        if '\n' in message:
            lines = message.rstrip('\n').split('\n')
            if kwargs['font'] == DEFAULT_FONT:
                line_height = DEFAULT_FONT_LINE_HEIGHT
            elif 'line_height' in kwargs:
                line_height = kwargs['line_height']
            else:
                line_height = text_size[1] / len(lines)
            for i, line in enumerate(message.rstrip('\n').split('\n')):
                self.text_right(y + (i * line_height), line, **kwargs)
        else:
            x = self.width - text_size[0]
            self.text((x, y), message, **kwargs)
        
    def text_centered(self, y, message, **kwargs):
        """Draw text, centered, at the given position on the canvas.

        The text will be centered on the canvas, with the top edge at
        the provided `y` position. If multiple lines are present in
        the message (newline separated), each line will be
        individually centered.

        """
        kwargs.setdefault('font', DEFAULT_FONT)
        text_size = self.textsize(message, font=kwargs['font'])
        if '\n' in message:
            lines = message.rstrip('\n').split('\n')
            if kwargs['font'] == DEFAULT_FONT:
                line_height = DEFAULT_FONT_LINE_HEIGHT
            elif 'line_height' in kwargs:
                line_height = kwargs['line_height']
            else:
                line_height = text_size[1] / len(lines)
            for i, line in enumerate(message.rstrip('\n').split('\n')):
                self.text_centered(y + (i * line_height), line, **kwargs)
        else:
            x = (self.width / 2) - (text_size[0] / 2)
            self.text((x, y), message, **kwargs)
        
    def __getattr__(self, key):
        """Proxy any other attributes (methods) to the canvas draw instance.
        """
        return getattr(self.draw, key)


class MicroPanelScreenBase:
    def __init__(self, width, height):
        """Initialize the base screen.
        
        Subclasses which override __init__() should call this function
        to ensure that the width and height are always set.

        """
        self.width = width
        self.height = height
        self.subscreen = None

    def draw(self):
        """Create an image representing the current state of this screen.

        This method should be overridden in a subclass.

        """
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
        """Draw the current subscreen, or screen, and return its image.
        """
        if self.subscreen is not None:
            img = self.subscreen.image
            if img:
                return img
        return self.draw()
        
    def process_event(self, event, payload):
        """Process an incoming event for this screen and its subscreen.
        
        This function is typically called by the plugin core and
        should not normally be overridden in a subclass. Subclasses
        should instead implement `handle_event()` and include the
        desired event in the `EVENTS` list.

        """
        r = set()
        if self.subscreen is not None:
            if self.subscreen.wants_event(event):
                r.update(self.subscreen.process_event(event, payload))

        # The subscreen wants to cancel itself
        if 'BACK' in r:
            self.subscreen = None
            r.remove('BACK')
            r.add('DRAW')
                
        if self.wants_event(event):
            r.update(self.handle_event(event, payload) or set())

        return r

    def process_button(self, label):
        """Process an incoming button press for this screen or its subscreen.

        This function is typically called by the plugin core and
        should not normally be overridden in a subclass. Subclasses
        should instead implement `handle_button()`.

        """
        r = set()
        if self.subscreen is not None:
            r.update(self.subscreen.process_button(label))

        if 'BACK' in r:
            self.subscreen = None
            r.remove('BACK')
            r.add('DRAW')
        elif not r:
            # We only handle the button press ourselves if the
            # subscreen didn't handle it (by returning a value)
            r.update(self.handle_button(label) or set())
            
        return r

    def get_canvas(self):
        """Create a new canvas instance for drawing a screen.
        """
        return MicroPanelCanvas(self.width, self.height)
