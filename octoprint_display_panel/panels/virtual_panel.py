import flask
import base64
from PIL import Image, ImageDraw
from io import BytesIO

import octoprint.plugin

import logging
logger = logging.getLogger("octoprint.plugins.display_panel.virtual_panel")


class VirtualPanelMixin(octoprint.plugin.SimpleApiPlugin,
                        octoprint.plugin.AssetPlugin):
    """Mixin class for the main plugin class to add API and assets for the
    virtual panel.

    IMPORTANT NOTE: This is a slightly odd way to implement this
    functionality; normally the OctoPrint plugin mixins would be
    included directly in the plugin's __init__.py. They are done here
    in order to co-locate the plugin API handler and the logic for
    managing the virtual panel. The key assumption is that the plugin
    will not need to use SimpleApiPlugin or AssetPlugin for any other
    functionality -- if this assumption is no longer correct, then it
    will be best to move the functions of this mixin into the main
    __init__.py and remove this mixin.

    """

    # This structure acts as a communication bridge between the
    # VirtualPanel class and the API methods below. Because these two
    # code paths typically execute in separate threads, a data
    # structure that can be referenced from both is needed to exchange
    # information. This structure is updated by the @classmethods
    # below, which are called from VirtualPanel. Button presses coming
    # through the API trigger the `button_callback`, while raw image
    # data is passed through `image_data`.
    _VP_ACTIVE_COMM = {
        'image_data': None,
        'button_callback': (lambda l: None)
    }

    @classmethod
    def vp_register_callback(cls, button_callback):
        """Set the callback to handle button presses coming from the API.
        """
        cls._VP_ACTIVE_COMM['button_callback'] = button_callback

    @classmethod
    def vp_set_image(cls, image):
        """Set the currently displayed image.
        """
        bio = BytesIO()
        image.save(bio, format='png')
        bio.seek(0)
        image_data = bio.read()
        image_encoded = base64.b64encode(image_data).decode('ascii')
        cls._VP_ACTIVE_COMM['image_data'] = 'data:image/png;base64,' + image_encoded

    # ~ SimpleApiPlugin
        
    def get_api_commands(self):
        """Return the list of supported API commands and data fields.
        """
        return {'press': ['button']}

    def on_api_command(self, command, data):
        """Handle an incoming API request.
        """
        self._logger.info(f'command was {command} and data {data}')
        if command == 'press':
            try:
                self._VP_ACTIVE_COMM['button_callback'](data['button'])
            except ValueError:
                return flask.abort(
                    400, f"{data['button']} is not a valid button name"
                )
        # We always return the current state of the display, which may
        # include updates based on a processed button press.
        return self.on_api_get(None)

    def on_api_get(self, request):
        """Return the current state of the display.
        """
        return flask.jsonify(image_data=self._VP_ACTIVE_COMM['image_data'])

    # ~ AssetPlugin
    
    def get_assets(self):
        """Return the assets needed to inject into the web user interface.
        """
        return {
            "js": ["js/display_panel.js"],
            "clientjs": ["clientjs/display_panel.js"]
        }


class VirtualPanel:
    """The virtual panel as shown in the web user interface.
    """
    def __init__(self, width, height, button_callback):
        VirtualPanelMixin.vp_register_callback(button_callback)
        self.width = width
        self.height = height
        self._hold_image = None
        self.fill(0)
        self.show()

    def shutdown(self):
        pass # not needed

    def fill(self, v):
        """Fill the virtual panel with the specified color.
        """
        self._image = Image.new("1", (self.width, self.height))
        if v != 0:
            draw = ImageDraw.Draw(self._image)
            draw.rectangle((0, 0, self.width, self.height), fill=v)

    def show(self):
        """Show the currently set image on the virtual panel.
        """
        VirtualPanelMixin.vp_set_image(self._image)

    def poweroff(self):
        """We can't power the virtual panel off, but we can blank it.
        """
        self._hold_image = self._image
        self.fill(0)
        self.show()

    def poweron(self):
        """Restore the virtual panel image from being blanked.
        """
        if self._hold_image is not None:
            self._image = self._hold_image
        self.show()
        self._hold_image = None

    def image(self, img):
        """Set a new image to be shown on the virtual panel.
        """
        if self._hold_image is None:
            self._image = img
        else:
            self._hold_image = img

