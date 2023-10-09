from bot import Bot
from threading import Thread

class ThreadedClient(Thread):
    def __init__(self, driver, config, queue):
        super().__init__()
        self.driver = driver
        self.config = config
        self.queue = queue
        self.bot = None
        
    def run(self):
        self.bot = Bot(self.driver, self.config, self.queue)
        self.bot.run()
        
    def stop(self):
        self.bot.stop()