import flask
from io import BytesIO

import octoprint.plugin


class VirtualPanelMixin(octoprint.plugin.SimpleApiPlugin):
    _VP_ACTIVE_COMM = {
        'image_data': None,
        'button_callback': (lambda l: None)
    }

    @classmethod
    def vp_register_callback(cls, button_callback):
        cls.ACTIVE_COMM['button_callback'] = button_callback

    @classmethod
    def vp_set_image(cls, image):
        bio = BytesIO()
        image.save(bio, format='png')
        bio.seek(0)
        image_data = b.read()
        cls.ACTIVE_COMM['image_data'] = image_data

    def get_api_commands(self):
        return {'press': ['button']}

    def on_api_command(self, command, data):
        self._logger.info(f'command was {command} and data {data}')
        self.ACTIVE_COMM['button_callback'](data['button'])

    def on_api_get(self, request):
        return flask.jsonify(display='foo',
                             image_data=cls.ACTIVE_COMM['image_data'])


class VirtualPanel:
    def __init__(self, width, height, button_callback):
        VirtualPanelMixin.vp_register_callback(button_callback)
        self.width = width
        self.height = height

    def shutdown(self):
        pass

    def fill(self, v):
        # TODO: fill
        pass

    def show(self):
        VirtualPanelMixin.vp_set_image(self.image)

    def poweroff(self):
        self.hold_image = self.image
        self.fill(0)

    def poweron(self):
        self.image = self.hold_image
        self.show()

    def image(self, img):
        self.image = img
