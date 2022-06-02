import inspect
import time
from typing import Any

from constants import *


def now():
    """
    return the current time in seconds
    """
    return round(time.time()*1000)

_START_TIME = now()

class Logger:
    name = "main"
    verbosity = LOG_INFO

    def __init__(self, name = "main") -> None:
        self.name = name
    
    def _log_message(self, ilevel, slevel, message):
        if ilevel == LOG_ALWAYS or self.verbosity >= ilevel :
            delta = now() - _START_TIME
            color = LOG_COLOR.get(slevel, LOG_COLOR.get("DEFAULT"))
            print(f"{str(delta).rjust(8)} [{self.name.ljust(8)}] \033[{color}{slevel.rjust(5)}\033[0m : {message}")

    def always(self, message):
        self._log_message(LOG_ALWAYS, "PRINT", message)

    def fatal(self, message):
        self._log_message(LOG_FATAL, "FATAL", message)

    def error(self, message):
        self._log_message(LOG_ERROR, "ERROR", message)

    def warning(self, message):
        self._log_message(LOG_WARNING, "WARN", message)

    def info(self, message):
        self._log_message(LOG_INFO, "INFO", message)

    def fine(self, message):
        self._log_message(LOG_FINE, "FINE", message)

    def debug(self, message):
        self._log_message(LOG_DEBUG, "DEBUG", message)

    def enter(self):
        caller = inspect.getouterframes( inspect.currentframe() )[1]
        args, _, _, values = inspect.getargvalues(caller.frame)
        params = ", ".join(f"{arg}={values[arg]}" for arg in args)
        self._log_message(LOG_DEBUG_METHOD, "DEBUG", f">>> {caller.function}({params})")

    def returns(self, value):
        caller = inspect.getouterframes( inspect.currentframe() )[1]
        self._log_message(LOG_DEBUG_METHOD, "DEBUG", f"<<< {caller.function} -> {value}")

    def debug_fine(self, message):
        self._log_message(LOG_DEBUG_FINE, "DEBUG", message)

    def debug_finer(self, message):
        self._log_message(LOG_DEBUG_FINER, "DEBUG", message)

    def debug_finest(self, message):
        self._log_message(LOG_DEBUG_FINEST, "DEBUG", message)


class MigrationLogger:

    logs = []

    def __init__(self, logs, no_logs_in_files = False) -> None:
        self.logs = logs
        self.no_logs_in_files = no_logs_in_files

    def yaml_add_comment(self, yml, key, level, message, before = True):
        if self.no_logs_in_files:
            return
    
        message = f"{COMMENT_PREFIX} {level} : " + f"\n{COMMENT_PREFIX} {level} : ".join(message.split('\n'))
        if key is None:
            yml.yaml_set_start_comment(message)
        elif before:
            yml.yaml_set_comment_before_after_key(key, before = message, indent = 0)
        else:
            yml.yaml_set_comment_before_after_key(key, after = message, indent = 0, after_indent = 0)

    def info(self, path: str, message: str, uuid: str=None, yml=None, key: str=None, before: bool=True) -> None:
        self.logs.append(InfoLog(path, uuid, message.split('\n')[0]))
        if yml is not None:
            self.yaml_add_comment(yml, key, "INFO", message, before)

    def warning(self, path: str, message: str, uuid: str=None, yml=None, key: str=None, before: bool=True) -> None:
        self.logs.append(WarnLog(path, uuid, message.split('\n')[0]))
        if yml is not None:
            self.yaml_add_comment(yml, key, "WARNING", message, before)

    def error(self, path: str, message: str, uuid: str=None, yml=None, key: str=None, before: bool=True) -> None:
        self.logs.append(ErrorLog(path, uuid, message.split('\n')[0]))
        if yml is not None:
            self.yaml_add_comment(yml, key, "ERROR", message, before)

class Log:
    time = now()
    file = ""
    uuid = None
    line = 0
    level = None
    message = ""
    def __init__(self, file, uuid, level, message) -> None:
        self.file = file
        self.uuid = uuid
        self.level = level
        self.message = message
        pass

class InfoLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "INFO ", message)    

class WarnLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "WARN ", message)    

class ErrorLog(Log):
    def __init__(self, file, uuid, message) -> None:
        super().__init__(file, uuid, "ERROR", message)    

