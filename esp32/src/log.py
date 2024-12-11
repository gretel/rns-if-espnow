from micropython import const
import sys
import time

LOG_DEBUG = const(10)
LOG_INFO = const(20)
LOG_WARNING = const(30)
LOG_ERROR = const(40)
LOG_CRITICAL = const(50)

class Logger:
    def __init__(self, name):
        self.name = name
        self.level = LOG_DEBUG

    def _log(self, level, msg, *args):
        if level >= self.level:
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