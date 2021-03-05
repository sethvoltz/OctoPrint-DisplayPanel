import time

from . import base


class SystemInfoScreen(base.MicroPanelScreenBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {}
        self.last_stats = 0
        self.get_stats()
        
    def draw(self):
        self.get_stats()
        load = self.stats['load']
        memory = self.stats['memory']
        disk = self.stats['disk']
        disk_percent = (disk.used / disk.total) * 100.0
        
        c = self.get_canvas()
        c.text_centered(0, ip)
        c.text((0, 9), f'L: {load[0]:.2f} {load[1]:.2f} {load[2]:.2f}')
        c.text((0, 18), (f'M: {mem.used//MB}/{mem.total//MB} MB'
                         f' {mem.percent}%'))
        
        c.text((0, 27), (f'D: {disk.used//GB}/{disk.total//GB} GB'
                         f' {disk_percent:.1f}%'))
        return c.image
               
    def get_stats(self):
        # Only get stats every 5 seconds
        if (time.time() - self.last_stats) < 5:
            return
        self.last_stats = time.time()
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.stats['ip'] = s.getsockname()[0]
            s.close()
        except OSError:
            self.stats['ip'] = 'IP unavailable'
        try:
            self.stats['load'] = psutil.getloadavg()
        except OSError:
            self.stats['load'] = (-1, 0, 0)
        self.stats['memory'] = psutil.virtual_memory()
        self.stats['disk'] = shutil.disk_usage('/')
        
    
