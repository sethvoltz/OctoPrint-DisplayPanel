

from . import base, system, printer

class MicroPanelScreenTop(base.MicroPanelScreenBase):
    def __init__(self, width, height):
        super().__init__(width, height)

        self.status_bar_height = 16
        if status_bar_on_top:
            self.status_bar_top = 0
        else:
            self.status_bar_top = height - self.status_bar_height
        self.status_bar_screen = printer.PrinterStatusBarScreen(
            width, self.status_bar_height)

        subscreen_height = height - self.status_bar_height
        self.screens = [
            system.SystemInfoScreen(width, subscreen_height),
            printer.PrinterInfoScreen(width, subscreen_height),
            printer.PrintStatusScreen(width, subscreen_height),
        ]
        self.current_screen = 0
        self.set_subscreen(self.screens[self.current_screen])

    def set_subscreen(self, screen):
        size = (self.width, self.height - self.status_bar_height)
        super().set_subscreen(screen, size=size)

    @property
    def image(self):
        if self.status_bar_top == 0:
            main_top = self.status_bar_height
        else:
            main_top = 0
            
        c = self.get_canvas()
        main_image = super().image
        c.image.paste(main_image, (0, main_top))
        if main_image.size[1] < self.height:
            c.image.paste(self.status_bar_screen.image, (0, status_bar_top))
        return c.image

    def handle_button(self, label):
        if label == 'menu':
            self.current_screen += 1
            self.current_screen %= len(self.screens)
            self.set_subscreen(self.screens[self.current_screen])
            return {'DRAW'}

        if label == 'play':
            # connect the printer, start the job, etc.
            return {'DRAW'}

        if label == 'pause':
            # pause the job
            return {'DRAW'}

        if label == 'cancel' and job_is_running:
            self.set_subscreen(printer.JobCancelScreen)
            return {'DRAW'}
