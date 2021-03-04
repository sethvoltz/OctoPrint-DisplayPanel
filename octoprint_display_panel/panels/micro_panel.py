
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
    width = 128
    height = 64
    
    def __init__(self, button_callback):
        self.button_event_callback = button_callback
        
    def setup(self, settings):
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

    def shutdown(self):
        for gpio_pin in self.input_pinset:
            if gpio_pin == -1:
                continue
            GPIO.remove_event_detect(gpio_pin)
            GPIO.cleanup(gpio_pin)
            
    def fill(self, v):
        self.disp.fill(v)

    def show(self):
        self.disp.show()

    def poweroff(self):
        self.disp.poweroff()

    def poweron(self):
        self.disp.poweron()

    def image(self, img):
        self.disp.image(img)

    def handle_gpio_event(self, channel):
        if channel not in self.input_pinset:
            return

        self.button_event_callback(self.input_pinset[channel])
