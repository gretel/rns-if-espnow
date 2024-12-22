from micropython import const
import json
import machine
from log import Logger, LOG_CRITICAL, LOG_ERROR, LOG_WARNING, LOG_INFO, LOG_DEBUG
from eventbus import EventBus

# Standard Hayes responses
OK = "OK"
ERROR = "ERROR"

# Extended responses
INVALID = "INVALID PARAMETER"
RESET = "RESET PENDING"

# Standard Hayes baudrates and additional high speeds
VALID_BAUDRATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]

class ATCommands:
    def __init__(self, config, bus, uart):
        self.config = config
        self.uart = uart
        self.log = Logger("AT")
        self.buffer = ""
        self.event_bus = bus

    def process_byte(self, byte):
        char = chr(byte)
        if char == '\r':
            if self.buffer:
                response = self.process_command(self.buffer.strip().upper())
                self.uart.write(f"{response}\r\n")
                self.buffer = ""
        elif char != '\n':
            self.buffer += char

    def process_command(self, cmd):
        """Process single AT command"""

        self.uart.write(f"\r\n") # linefeed
        # Basic commands
        if cmd == "AT": return OK
        if cmd == "ATI": return self._get_info()
        if cmd == "AT&F": return self._factory_reset()
        if cmd == "AT&V": return self._view_config()
        if cmd == "AT&W": return self.config.save()
        # TODO: add stats from espnow
        
        # Configuration commands
        if cmd.startswith("AT+DESC="): return self._set_description(cmd[8:])
        if cmd.startswith("AT+BAUD="): return self._set_baudrate(cmd[8:])
        if cmd.startswith("AT+CHAN="): return self._set_channel(cmd[8:])
        if cmd.startswith("AT+MAC="): return self._set_mac(cmd[7:])
        if cmd.startswith("AT+LOG="): return self._set_loglevel(cmd[7:])
        if cmd.startswith("AT+PROTO="): return self._set_protocol(cmd[9:])
        if cmd.startswith("AT+PINS="): return self._set_pins(cmd[7:])
        if cmd == "AT+RESET": return self._reset()
        
        return ERROR

    def _get_info(self):
        return f"RNSNOW\r\nOK" # TODO

    def _view_config(self):
        return json.dumps(self.config.data)

    def _factory_reset(self):
        self.config.reset()
        return RESET

    def _set_description(self, value):
        try:
            desc = value.strip('"')
            if len(desc) > 255:
                return INVALID
            self.config.description = desc
            return OK
        except:
            return ERROR

    def _set_baudrate(self, value):
        try:
            baud = int(value)
            if baud not in VALID_BAUDRATES:
                return INVALID
            self.config.baudrate = baud
            self.event_bus.emit('ch_bd', baud)
            return RESET
        except:
            return ERROR

    def _set_channel(self, value):
        try:
            chan = int(value)
            if not 1 <= chan <= 14:
                return INVALID
            self.config.channel = chan
            self.event_bus.emit('ch_ch', chan)
            return RESET
        except:
            return ERROR

    def _set_mac(self, value):
        try:
            if len(value) != 12:
                return INVALID
            # Validate hex
            int(value, 16)
            self.config.mac = value
            return OK
        except:
            return ERROR

    def _set_loglevel(self, value):
        try:
            level = int(value)
            if level not in [LOG_CRITICAL, LOG_ERROR, LOG_WARNING, LOG_INFO, LOG_DEBUG]:
                return INVALID
            self.config.loglevel = level
            self.log.level = level
            return OK
        except:
            return ERROR

    def _set_protocol(self, value):
        value = value.lower()
        if value not in ["default", "lr"]:
            return INVALID
        self.config.protocol = value
        return AT&W

    def _set_pins(self, value):
        try:
            parts = value.split(",")
            if len(parts) != 2:
                return INVALID
            pin_name = parts[0].lower()
            pin_val = None if parts[1] == "NONE" else int(parts[1])
            
            if pin_name not in ["led", "button1", "button2", "tx", "rx"]:
                return INVALID
                
            self.config.data["pins"][pin_name] = pin_val
            return RESET
        except:
            return ERROR

    def _reset(self):
        """Log and reset device"""
        self.log.info("Reset triggered via AT command")
        machine.reset()