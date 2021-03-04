import flask
import base64
from PIL import Image, ImageDraw
from io import BytesIO

import octoprint.plugin

import logging
logger = logging.getLogger("octoprint.plugins.display_panel.virtual_panel")


class VirtualPanelMixin(octoprint.plugin.SimpleApiPlugin,
                        octoprint.plugin.AssetPlugin):
    _VP_ACTIVE_COMM = {
        'image_data': None,
        'button_callback': (lambda l: None)
    }

    @classmethod
    def vp_register_callback(cls, button_callback):
        cls._VP_ACTIVE_COMM['button_callback'] = button_callback

    @classmethod
    def vp_set_image(cls, image):
        bio = BytesIO()
        image.save(bio, format='png')
        bio.seek(0)
        image_data = bio.read()
        image_encoded = base64.b64encode(image_data).decode('ascii')
        cls._VP_ACTIVE_COMM['image_data'] = 'data:image/png;base64,' + image_encoded

    def get_api_commands(self):
        return {'press': ['button']}

    def on_api_command(self, command, data):
        self._logger.info(f'command was {command} and data {data}')
        self._VP_ACTIVE_COMM['button_callback'](data['button'])

    def on_api_get(self, request):
        return flask.jsonify(image_data=self._VP_ACTIVE_COMM['image_data'])

    def get_assets(self):
        return {
            "js": ["js/display_panel.js"],
            "clientjs": ["clientjs/display_panel.js"]
        }


class VirtualPanel:
    def __init__(self, width, height, button_callback):
        VirtualPanelMixin.vp_register_callback(button_callback)
        self.width = width
        self.height = height
        self._hold_image = None
        self.fill(0)
        self.show()

    def shutdown(self):
        pass

    def fill(self, v):
        self._image = Image.new("1", (self.width, self.height))
        if v != 0:
            draw = ImageDraw.Draw(self._image)
            draw.rectangle((0, 0, self.width, self.height), fill=v)

    def show(self):
        VirtualPanelMixin.vp_set_image(self._image)

    def poweroff(self):
        self._hold_image = self._image
        self.fill(0)
        self.show()

    def poweron(self):
        if self._hold_image is not None:
            self._image = self._hold_image
        self.show()
        self._hold_image = None

    def image(self, img):
        self._image = img
        self._hold_image = None
