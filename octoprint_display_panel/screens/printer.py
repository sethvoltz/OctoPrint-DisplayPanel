

from . import base


# TODO: either fully implement this or think of some other way to get
#       _printer from the main plugin up to this module
#
#class OctoPrintPrinterProxy:
#    def __init__(self):
#        self._printer = None
#
#    def __getattr__(self, key):
#        if self._printer:
#            return getattr(self._printer, key)
#
#    def set(self, printer):
#        self._printer = printer
#        
#PRINTER = OctoPrintPrinterProxy()


class PrinterInfoScreen(base.MicroPanelScreenBase):
    def draw(self):
        c = self.get_canvas()
        c.text((0, 0), "Printer Temperatures")
        head_text = "no printer"
        bed_text = "no printer"
        
        if PRINTER.get_current_connection()[0] != 'Closed':
            temperatures = PRINTER.get_current_temperatures()
            tool = temperatures['tool0']
            if tool:
                head_text = f"{tool['actual']} / {tool['target']}\xb0C"
            else:
                head_text = "no tool"
                
            bed = temperatures['bed']
            if bed:
                bed_text = f"{bed['actual']} / {bed['target']}\xb0C"
            else:
                bed_text = "no bed"
        c.text((0, 9), head_text)
        c.text((0, 18), bed_text)

        return c.image


class PrintStatusScreen(base.MicroPanelScreenBase):
    def draw(self):
        c = self.get_canvas()
        c.text((0, 0), f"State: {PRINTER.get_state_string()}")

        current_data = PRINTER.get_current_data()
        if current_data['job']['file']['name']:
            c.text((0, 9), f"File: {current_data['job']['file']['name']}")
            
            print_time = get_time_from_seconds(
                current_data['progress']['printTime'] or 0)
            c.text((0, 18), f"Time: {print_time}")
            
            filament = (current_data['job']['filament']['tool0']
                        if 'tool0' in current_data['job']['filament']
                        else current_data['job']['filament'])
            filament_length = float_count_formatter(
                (filament['length'] or 0) / 1000, 3)
            filament_mass = float_count_formatter(
                (filament['volume'] or 0), 3)
            c.text((0, 27), f"Filament: {filament_length}m/{filament_mass}cm3")

            # TODO: Add DisplayLayerProgress data
            
        else:
            c.text((0, 18), "Waiting for file...")
            

class PrinterStatusBarScreen(base.MicroPanelScreenBase):
    # from update_ui_bottom()
    pass
