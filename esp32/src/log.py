from micropython import const
import sys
import time

# Log levels aligned with syslog severity levels
LOG_CRITICAL = const(0)    # Critical: critical conditions
LOG_ERROR = const(1)       # Error: error conditions
LOG_WARNING = const(2)     # Warning: warning conditions
LOG_INFO = const(3)        # Informational: normal operational messages  
LOG_DEBUG = const(4)       # Debug: debug-level messages

class LogManager:
    _instance = None
    _level = LOG_INFO
    
    @staticmethod
    def get_instance():
        if not LogManager._instance:
            LogManager._instance = LogManager()
        return LogManager._instance
        
    @property
    def level(self):
        return self._level
        
    @level.setter 
    def level(self, value):
        if 0 <= value <= 4:
            self._level = value

class Logger:
    def __init__(self, name):
        self.name = name
        self.manager = LogManager.get_instance()

    def _log(self, level, msg, *args):
        if level <= self.manager.level:
            if args:
                msg = msg % args
            print(f"[{time.ticks_ms():010d}] {self._level_name(level):8s} - {self.name} - {msg}")

    def _level_name(self, level):
        if level == LOG_DEBUG: return "DEBUG"
        if level == LOG_INFO: return "INFO"
        if level == LOG_WARNING: return "WARNING" 
        if level == LOG_ERROR: return "ERROR"
        if level == LOG_CRITICAL: return "CRITICAL"
        return "UNKNOWN"

    def debug(self, msg, *args): self._log(LOG_DEBUG, msg, *args)
    def info(self, msg, *args): self._log(LOG_INFO, msg, *args)
    def warning(self, msg, *args): self._log(LOG_WARNING, msg, *args)
    def error(self, msg, *args): self._log(LOG_ERROR, msg, *args)
    def critical(self, msg, *args): self._log(LOG_CRITICAL, msg, *args)
    def exc(self, e, msg=None):
        if msg:
            self.error(msg)
        sys.print_exception(e)