from micropython import const
import json
import os
from log import LOG_INFO, Logger

DEFAULT_CONFIG = {
    "description": "",
    "pins": {
        "led": 10,
        "button1": 37,
        "button2": None,
        "tx": 26,
        "rx": 25
    },
    "loglevel": LOG_INFO,
    "channel": 6,
    "mac": "ffffffffffff",
    "protocol": "default",  # or "lr"
    "baudrate": 115200
}

CONFIG_FILE = "config.json"

class Config:
    def __init__(self):
        self.log = Logger("Config")
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        try:
            if CONFIG_FILE in os.listdir():
                with open(CONFIG_FILE) as f:
                    stored = json.load(f)
                    self.data.update(stored)
                self.log.info("Loaded configuration from %s: %s", CONFIG_FILE, self.data)
        except Exception as e:
            self.log.exc(e, "Error loading config")
            
    def save(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.data, f)
            self.log.info("Saved configuration to %s:\n%s", CONFIG_FILE, self.data)

            return True
        except Exception as e:
            self.log.exc(e, "Error saving config")
            return False

    @property 
    def description(self): return self.data["description"]
    @description.setter
    def description(self, value): 
        self.data["description"] = value[:255]
    
    @property
    def led_pin(self): return self.data["pins"]["led"]
    @property
    def button1_pin(self): return self.data["pins"]["button1"] 
    @property
    def button2_pin(self): return self.data["pins"]["button2"]
    @property
    def tx_pin(self): return self.data["pins"]["tx"]
    @property
    def rx_pin(self): return self.data["pins"]["rx"]
    
    @property
    def loglevel(self): return self.data["loglevel"]
    @loglevel.setter
    def loglevel(self, value): self.data["loglevel"] = value
    
    @property
    def channel(self): return self.data["channel"]
    @channel.setter
    def channel(self, value): self.data["channel"] = value
    
    @property 
    def mac(self): 
        mac_str = self.data["mac"]
        return bytes.fromhex(mac_str)
    @mac.setter
    def mac(self, value):
        if isinstance(value, bytes):
            self.data["mac"] = value.hex()
        else:
            self.data["mac"] = value
            
    @property
    def protocol(self): return self.data["protocol"]
    @protocol.setter
    def protocol(self, value): self.data["protocol"] = value
    
    @property
    def baudrate(self): return self.data["baudrate"]
    @baudrate.setter
    def baudrate(self, value): self.data["baudrate"] = value