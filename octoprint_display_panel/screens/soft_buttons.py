import os.path
from octoprint.events import Events

from . import base

from logging import getLogger


class SoftButtonsScreen(base.MicroPanelScreenScroll):
    _logger = getLogger('octoprint.plugins.display_panel.soft_buttons')
    
    def __init__(self, width, height, _printer, _settings):
        menu = [
            'Auto Home',
            'Bed Leveling',
            'Filament Unload',
            'Filament Load',
            'Cooldown'
        ]
        super().__init__(width, height, 'Soft Buttons', menu)
        self._printer = _printer
        self._settings = _settings
        
    def handle_menu_item(self, menu_item):
        if self._printer.is_disconnected():
            return
        
        if menu_item == 'Auto Home':
            self._printer.commands('G28')
        elif menu_item == 'Bed Leveling':
            self._printer.commands([
                'M140 S50', 'G28', 'M190',
                'G0 X30 Y30 Z1', 'G0 Z0', 'M0 Point 1',
                'G0 X30 Y200 Z1', 'G0 Z0', 'M0 Point 2',
                'G0 X200 Y200 Z1', 'G0 Z0', 'M0 Point 3',
                'G0 X200 Y30 Z1', 'G0 Z0', 'M0 Point 4',
                'G28'
            ])
        elif menu_item == 'Filament Load':
            self._printer.commands('M701 L10')
        elif menu_item == 'Filament Unload':
            self._printer.commands('M702 U10')
        elif menu_item == 'Cooldown':
            self._printer.commands(['M104 S0', 'M140 S0'])
        return {'DRAW'}


class FileSelectScreen(base.MicroPanelScreenScroll):
    _logger = getLogger('octoprint.plugins.display_panel.file_select')
    
    def __init__(self, width, height, _printer, _file_manager):
        self._printer = _printer
        self._file_manager = _file_manager
        self.folder = ""
        super().__init__(width, height, 'File Select', [])
        self.refresh_menu()
        
    def refresh_menu(self):
        m = {}
        files = self._file_manager.list_files(destinations='local',
                                              path=self.folder)['local']
        if self.folder:
            m['../'] = 9e999
        for name, metadata in files.items():
            self._logger.info(f'{name}: {repr(metadata)}')
            if 'type' not in metadata:
                continue
            # skip files which have completed successfully
            if 'history' in metadata and any(h.get('success')
                                             for h in metadata['history']):
                continue
            if metadata['type'] == 'folder':
                m[name + '/'] = 9e999
            elif metadata['type'] == 'machinecode':
                m[name] = metadata['date']
            # TODO: support type == 'model', aka stl
        current_selection = (
            self.menu[self.selection] if self.menu else None
        )
        self.menu = [
            k for k, v in sorted(m.items(), key=(lambda i: (-i[1], i[0])))
        ]
        if current_selection in self.menu:
            self.selection = self.menu.index(current_selection)
        else:
            self.selection = 0

    EVENTS = [Events.UPDATED_FILES]
            
    def handle_event(self, event, payload):
        self.refresh_menu()

    def handle_menu_item(self, menu_item):
        if menu_item.endswith('/'):
            self.folder = os.path.normpath(
                os.path.join(self.folder, menu_item.rstrip('/')))
            if self.folder == '.':
                self.folder = ''
            self.refresh_menu()
            return {'DRAW'}

        if self._printer.is_disconnected():
            return

        self._printer.select_file(menu_item, False, printAfterSelect=False)
        return {'DRAW'}
        
