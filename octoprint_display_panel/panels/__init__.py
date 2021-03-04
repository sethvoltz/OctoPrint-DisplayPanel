try:
    from . import micro_panel
except (NotImplementedError, ImportError):
    micro_panel = None

from . import virtual_panel

import logging
logger = logging.getLogger("octoprint.plugins.display_panel.virtual_panel")


class Panels:
    # These are default values in case the MicroPanel is not
    # initialized. The VirtualPanel will always have the same
    # dimensions as the MicroPanel (or any other variant of a hardware
    # panel).
    width = 128
    height = 64

    def __init__(self, settings, button_callback):
        self.panels = []
        if micro_panel is not None:
            panel = micro_panel.MicroPanel(button_callback)
            panel.setup(settings)
            self.width, self.height = panel.width, panel.height
            self.panels.append(panel)

        # TODO: make dependent on a setting
        if True:
            panel = virtual_panel.VirtualPanel(self.width, self.height,
                                               button_callback)
            self.panels.append(panel)

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
