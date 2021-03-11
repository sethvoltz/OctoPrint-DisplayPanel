import os.path
from octoprint.events import Events

from . import base

from logging import getLogger


class SoftButtonsScreen(base.MicroPanelScreenScroll):
    _logger = getLogger('octoprint.plugins.display_panel.soft_buttons')
    
    def __init__(self, width, height, _printer, _settings):
        super().__init__(width, height, 'Soft Buttons', [],
                         empty_text="None - add in settings")
        self._printer = _printer
        self._settings = _settings
        self.refresh_menu()

    def refresh_menu(self):
        self.menu = [
            i['label'] for i in self._settings.get(['soft_buttons'],
                                                   merged=True)
        ]
        
    def handle_menu_item(self, menu_item):
        # don't run GCODE if the printer is disconnected
        if self._printer.is_disconnected():
            return

        for i in self._settings.get(['soft_buttons'], merged=True):
            if menu_item == i['label']:
                commands = [
                    c.strip() for c in i['gcode'].split(';')
                ]
                self._printer.commands(commands)
                
        return {'DRAW'}

    EVENTS = [Events.SETTINGS_UPDATED]

    def handle_event(self, event, payload):
        self.refresh_menu()
        return {'DRAW'}
    

class FileSelectScreen(base.MicroPanelScreenScroll):
    _logger = getLogger('octoprint.plugins.display_panel.file_select')
    
    def __init__(self, width, height, _printer, _file_manager, _settings):
        self._printer = _printer
        self._file_manager = _file_manager
        self._settings = _settings
        self.folder = ""
        super().__init__(width, height, 'File Select', [])
        self.refresh_menu()
        
    def refresh_menu(self):
        m = {}
        files = self._file_manager.list_files(destinations='local',
                                              path=self.folder)['local']
        skip_completed = bool(self._settings.get(["file_select_hide_complete"]))
        if self.folder:
            m['../'] = 9e999
        for name, metadata in files.items():
            if 'type' not in metadata:
                continue
            
            # skip files which have completed successfully
            if (skip_completed and 'history' in metadata
                and any(h.get('success') for h in metadata['history'])):
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

    EVENTS = [Events.UPDATED_FILES, Events.SETTINGS_UPDATED]
            
    def handle_event(self, event, payload):
        self.refresh_menu()
        return {'DRAW'}

    def handle_menu_item(self, menu_item):
        if menu_item.endswith('/'):
            self.folder = os.path.normpath(
                os.path.join(self.folder, menu_item.rstrip('/')))
            if self.folder == '.':
                self.folder = ''
            self._logger.info(f'Selected directory: {menu_item}')
            self.refresh_menu()
            return {'DRAW'}

        # don't select a file if the printer is disconnected
        if self._printer.is_disconnected():
            return

        self._logger.info(f'Selected file: {menu_item}')
        self._printer.select_file(menu_item, False, printAfterSelect=False)
        return {'DRAW'}
        
