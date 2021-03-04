
from board import SCL, SDA
import busio
import adafruit_ssd1306
import RPi.GPIO as GPIO


def bcm2board(bcm_pin):
    pinmap = [-1, -1, -1,  7, 29, 31, -1, -1, -1, -1, -1, 32,
              33, -1, -1, 36, 11, 12, 35, 38, 40, 15, 16, 18,
              22, 37, 13]
    if bcm_pin != -1:
        return pinmap[bcm_pin - 1]
    return -1


class MicroPanel:
    """Interface to the standard I2C and GPIO-driven Micro Panel.
    """
    width = 128
    height = 64
    
    def __init__(self, button_callback):
        self.button_event_callback = button_callback
        self.gpio_pinset = set()
        
    def setup(self, settings):
        """Apply settings from OctoPrint's SettingsPlugin mixin to
        configure the panel.
        """
        self.i2c_address = int(settings.get(['i2c_address'], merged=True), 0)
        self.input_pinset = {
            settings.get_int([f'pin_{p}'], merged=True): p
            for p in ['cancel', 'mode', 'pause', 'play']
        }
        self.debounce_time = settings.get_int(['debounce'], merged=True)
    
        # set up display
        self.i2c = busio.I2C(SCL, SDA)
        self.disp = adafruit_ssd1306.SSD1306_I2C(
            self.width, self.height, self.i2c, addr=self.i2c_address)

        # set up GPIO mode
        current_mode = GPIO.getmode()
        if current_mode is None:
            # set GPIO to BCM numbering
            GPIO.setmode(GPIO.BCM)

        elif current_mode != GPIO.BCM:
            # remap to BOARD numbering
            GPIO.setmode(current_mode)
            self.input_pinset = {bcm2board(p): l
                                 for p, l in self.input_pinset.items()}
        GPIO.setwarnings(False)

        # set up pins
        for gpio_pin in self.input_pinset:
            if gpio_pin == -1:
                continue

            GPIO.setup(gpio_pin, GPIO.IN, GPIO.PUD_UP)
            GPIO.remove_event_detect(gpio_pin)
            GPIO.add_event_detect(gpio_pin, GPIO.FALLING,
                                  callback=self.handle_gpio_event,
                                  bouncetime=self.debounce_time)
            self.gpio_pinset.add(gpio_pin)

        # clean up any pins that may not be selected any more
        cleaned_pins = set()
        for gpio_pin in self.gpio_pinset.difference(self.input_pinset.keys()):
            try:
                GPIO.remove_event_detect(gpio_pin)
                GPIO.cleanup(gpio_pin)
            except:
                logger.exception(f'failed to clean up GPIO pin {gpio_pin}')
            else:
                cleaned_pins.add(gpio_pin)
        self.gpio_pinset.difference_update(cleaned_pins)

    def shutdown(self):
        """Called during plugin shutdown.
        """
        for gpio_pin in self.input_pinset:
            if gpio_pin == -1:
                continue
            GPIO.remove_event_detect(gpio_pin)
            GPIO.cleanup(gpio_pin)
            
    def fill(self, v):
        """Fill the screen with the specified color.
        """
        self.disp.fill(v)

    def image(self, img):
        """Set an image to be shown on screen.
        """
        self.disp.image(img)

    def show(self):
        """Show the currently set image on the screen.
        """
        self.disp.show()

    def poweroff(self):
        """Turn the display off.
        """
        self.disp.poweroff()

    def poweron(self):
        """Turn the display on.
        """
        self.disp.poweron()

    def handle_gpio_event(self, channel):
        """Called on a GPIO event, translate an input channel to a button label
        and invokes the button callback function with that label.
        """
        if channel not in self.input_pinset:
            return

        self.button_event_callback(self.input_pinset[channel])
