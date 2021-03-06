# Copyright (c) 2020 Kaamiki Development Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# ======================================================================

"""Utility for logging all Kaamiki events."""

import getpass
import logging
import os
import sys
from distutils.sysconfig import get_python_lib
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Tuple

_SysExcInfoType = Tuple[type, BaseException, TracebackType]

USER = getpass.getuser().lower().replace(" ", "-")


class Neo(type):
  """
  A naive implementation of Singleton design pattern.

  Singleton is a creational design pattern, which ensures that
  only a single object of its kind exist and provides a single
  point of access to it for any other code.
  The below is a non thread-safe implementation of a Singleton
  design pattern. You can instantiate a class multiple times
  and yet you would get reference to the same object.

  See https://stackoverflow.com/q/6760685 for more methods of
  implementing singletons in code.

  Example:
    >>> class YourClass(metaclass=Neo):
    ...     pass
    ...
    >>> singleton_obj1 = YourClass()
    >>> singleton_obj2 = YourClass()
    >>> singleton_obj1
    <__main__.YourClass object at 0x7fc8f1948970>
    >>> singleton_obj2
    <__main__.YourClass object at 0x7fc8f1948970>
  """
  # See https://refactoring.guru/design-patterns/singleton/python/example
  # for a thread-safe implementation.
  _instances = {}

  def __call__(cls, *args, **kwargs):
    """Callable instance of a class."""
    if cls not in cls._instances:
      cls._instances[cls] = super().__call__(*args, **kwargs)
    return cls._instances[cls]


class ModulePath(object):
  """
  Resolve relative path of the logged module.

  The implementation of fetching or resolving relative module
  path is inspired from Sprint Boot, wherein it displays the
  module name which is logging the record.
  """

  def __init__(self, path: str) -> None:
    """
    Instantiate class.

    Args:
      path: Absolute path of the module.
    """
    self._path = path

  @property
  def resolve(self) -> str:
    """Return relative path of the logged module."""
    delimiter = "kaamiki" if "kaamiki" in self._path else get_python_lib()
    module = self._path.partition(delimiter)[-1]
    return os.path.splitext(module.replace("/" or "\\", "."))[0][1:]


class LogFormatter(logging.Formatter, metaclass=Neo):
  """
  Format logs gracefully.

  The `LogFormatter` is a formatter class for formatting the
  logs across multiple levels. It provides an uniform way of
  logging records across including exceptions.
  """

  def __init__(self) -> None:
    """Instantiate class."""
    self._timestamp_format = "%a %b %d, %Y %H:%M:%S"
    self._log_format = ("%(asctime)s.%(msecs)03d %(levelname)8s "
                        "%(process)07d {:>30} : %(message)s")
    self._exc_format = "{0} caused due to {1} {2}on line {3}."

  @staticmethod
  def formatException(exc_info: _SysExcInfoType) -> str:
    """Format traceback message into string representation."""
    return repr(super().formatException(exc_info))

  def format(self, record: logging.LogRecord) -> str:
    """Format output log message."""
    module = ModulePath(record.pathname).resolve
    # Shorten longer module names with an ellipsis while logging.
    # This ensures length of module name stay consistent in logs.
    if len(module) > 30:
      module = module[:27] + bool(module[27:]) * "..."

    raw = logging.Formatter(self._log_format.format(module),
                            self._timestamp_format).format(record)

    if record.exc_text:
      function = record.funcName
      function = f"in {function}() " if function != "<module>" else ""
      exc_msg = self._exc_format.format(record.exc_info[1].__class__.__name__,
                                        str(record.msg).lower(),
                                        function,
                                        record.exc_info[2].tb_lineno)
      raw = raw.replace("\n", "").replace(str(record.exc_info[-2]), exc_msg)
      raw, _, _ = raw.partition("Traceback")

    return raw


class StreamFormatter(logging.StreamHandler, metaclass=Neo):
  """
  Stream colored logs.

  StreamFormatter is a traditional logging stream handler with
  some added colors and taste of Singleton design pattern. The
  colors change themselves with respect to the logging levels.
  """
  # TODO(xames3): Consider adding support to Windows systems.
  # See https://gist.github.com/mooware/a1ed40987b6cc9ab9c65
  # for implementation for a Windows machine.
  _DEFAULT = "\033[0m"
  _RED = "\033[91m"
  _GREEN = "\033[92m"
  _YELLOW = "\033[93m"
  _CYAN = "\033[96m"
  _BOLD = "\033[1m"

  _color_levels = {
      logging.DEBUG: _CYAN,
      logging.INFO: _GREEN,
      logging.WARNING: _YELLOW,
      logging.ERROR: _RED,
      logging.CRITICAL: _RED,
  }

  def __init__(self) -> None:
    """Instantiate class."""
    super().__init__(sys.stdout)

  @classmethod
  def _render_color(cls, level: int, record: logging.LogRecord) -> str:
    """Returns color to render while printing logs."""
    return cls._color_levels.get(level, cls._DEFAULT) + record.levelname

  def format(self, record: logging.LogRecord) -> str:
    """Format log level with adaptive color."""
    _record = logging.StreamHandler.format(self, record)
    _colored = self._render_color(record.levelno, record) + self._DEFAULT
    return _record.replace(record.levelname, _colored)


class ArchiveHandler(RotatingFileHandler, metaclass=Neo):
  """
  Archive logs which grow in size.

  The `ArchiveHandler` is a rotating file handler class which
  creates an archive of the log to rollover once it reaches a
  predetermined size. When the log is about to exceed the set
  size, the current log is closed and a new log file is taken
  up for further logging.
  This class ensures that the logs won't grow indefinitely.
  """

  def __init__(self,
               name: str,
               mode: str = "a",
               size: int = 0,
               backups: int = 0,
               encoding: str = None,
               delay: bool = False) -> None:
    """
    Instantiate class.

    Args:
      name: Name of the log file.
      mode: Log file writing mode.
      size: Maximum file size limit for backup.
      backups: Total number of backup.
      encoding: File encoding.
      delay: Delay for backup.
    """
    self._count = 0
    super().__init__(filename=name,
                     mode=mode,
                     maxBytes=size,
                     backupCount=backups,
                     encoding=encoding,
                     delay=delay)

  def doRollover(self) -> None:
    """Does a rollover."""
    if self.stream:
      self.stream.close()

    if not self.delay:
      self.stream = self._open()

    self._count += 1
    self.rotate(self.baseFilename, f"{self.baseFilename}.{self._count}")


class SilenceOfTheLogs(object):
  """
  Log all Kaamiki events silently.

  The `SilenceOfTheLogs` is a custom logger which records all
  Kaamiki events silently. The logger is packed with Rotating
  file handler and a custom formatter which enables sequential
  archiving and clean log formatting.

  Example:
    >>> from kaamiki.utils.logger import SilenceOfTheLogs
    >>> log = SilenceOfTheLogs().log
    >>> try:
    ...     5 / 0
    ... except Exception as error:
    ...     log.exception(error)
    ...
    Sun May 31, 2020 ... ERROR 0310595 ...: ZeroDivisionError caused ...
  """

  def __init__(self,
               name: str = None,
               level: str = "debug",
               size: int = None,
               backups: int = None) -> None:
    """
    Instantiate class.

    Args:
      name: Name for log file.
      level: Default logging level to log messages.
      size: Maximum file size limit for backup.
      backups: Total number of backup.
    """
    try:
      self._py = os.path.abspath(sys.modules["__main__"].__file__)
    except AttributeError:
      self._py = "kaamiki.py"

    self._name = name.lower() if name else Path(self._py.lower()).stem
    self._name = self._name.replace(" ", "-")
    self._level = level.upper()
    self._size = int(size) if size else 1000000
    self._backups = int(backups) if backups else 0

    self._logger = logging.getLogger()
    self._logger.setLevel(self._level)

    self._path = os.path.expanduser(f"~/.kaamiki/{USER}/logs/")

    if not os.path.exists(self._path):
      os.makedirs(self._path)

    self._file = os.path.join(self._path, "".join([self._name, ".log"]))
    self._formatter = LogFormatter()

  @property
  def log(self) -> logging.Logger:
    """Log Kaamiki events."""
    # Archive the logs once their file size reaches 1 Mb.
    # See ArchiveHandler() for more informations.
    file_handler = ArchiveHandler(self._file,
                                  size=self._size,
                                  backups=self._backups)
    stream_handler = StreamFormatter()
    file_handler.setFormatter(self._formatter)
    stream_handler.setFormatter(self._formatter)
    self._logger.addHandler(file_handler)
    self._logger.addHandler(stream_handler)
    return self._logger
