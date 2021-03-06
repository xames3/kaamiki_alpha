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

"""Collection of protocols which run in the background."""

import os
import random
import re
import sys
import time
import uuid
from subprocess import PIPE, Popen
from typing import Optional, Tuple

from kaamiki.utils.common import CSVDataWriter, now, seconds_to_datetime
from kaamiki.utils.logger import USER, Neo, SilenceOfTheLogs

_random = random.Random()
_random.seed(69)
_user_id = uuid.UUID(int=_random.getrandbits(128))

logger = SilenceOfTheLogs


class BabyMonitorProtocol(object, metaclass=Neo):
  """
  A protocol for logging all user activities.

  The `BabyMonitorProtocol` is a daemon class running in the
  background to observe and record everything the user tends
  to interacts with on the screen.
  The protocol monitors everything like the program(s) used,
  sites browsed by the user, etc. and how much time the user
  has spent on each of his/her task while using the machine.
  """

  def __init__(self, refresh: float = 1.0, level: str = "info") -> None:
    """Instantiate class."""
    self._refresh = refresh

    self._name = "Baby Monitor Protocol"
    self.log = logger(self._name, level).log

    if os.name == "nt":
      try:
        import comtypes
        import psutil

        import pywinauto
        from win32gui import GetForegroundWindow, GetWindowText
        from win32process import GetWindowThreadProcessId
        from win32api import GetFileVersionInfo as _info

        self.log.debug("Windows packages loaded successfully.")
        self._os = "nt"
        self._uia = pywinauto.Application(backend="uia")
        self._omnibox_title = "Address and search bar"
      except ImportError as error:
        self.log.error(f"{self._name} cannot load windows imports.")
        self.log.exception(error)
        del self
        sys.exit(0)
    elif os.name == "darwin":
      # TODO(xames3): Consider adding support for MacOS builds.
      self._os = "darwin"
      pass
    else:
      self._os = "posix"

    self._path = os.path.expanduser(f"~/.kaamiki/{USER}/data/activities/")

    if not os.path.exists(self._path):
      self.log.debug("Creating base directory for saving user data...")
      os.makedirs(self._path)

    self._csv = CSVDataWriter(os.path.join(self._path, f"{_user_id}.csv"))
    self._headers = ["window", "program", "url", "domain", "started",
                     "stopped", "spent", "days", "hours", "minutes",
                     "seconds"]

    self._active_window = {
        "nt": self._get_active_window_on_nt,
        "posix": self._get_active_window_on_posix,
        "darwin": self._get_active_window_on_darwin,
    }

    self._active_url = {
        "nt": self._get_active_url_on_nt,
        "posix": self._get_active_url_on_posix,
        "darwin": self._get_active_url_on_darwin,
    }

  def _get_active_window_on_nt(self) -> Tuple[Optional[str], ...]:
    """Return details of the active window on windows platform."""
    # See https://stackoverflow.com/a/47936739 for reference code.
    # pyright: reportUndefinedVariable=false
    window, program = GetForegroundWindow(), None
    pid = GetWindowThreadProcessId(window)[-1]
    # We are considering only one active instance of a process.
    # Even if the parent process spawns multiple child processes
    # this check ensures that we do not record instances of a
    # process that were not interacted by the user.
    if psutil.pid.exists(pid):
      window = GetWindowText(window)
      # Skip `Task Switching` program and other program
      # switching overlays that are invoked with `Alt + Tab`.
      window = window if window != "Task Switching" else None
      path = psutil.Process(pid).exe()
      # See https://stackoverflow.com/a/31119785 for using
      # windows resource table for parsing program name.
      try:
        lang, page = _info(path, "\\VarFileInfo\\Translation")[0]
        addr = "%04X%04X" % (lang, page)
        file = u"\\StringFileInfo\\{}\\FileDescription".format(addr)
        program = _info(path, file)
      except NameError:
        self.log.error(f"{self._name} couldn't resolve program name.")
        window, program = None, None

    return window, program

  def _get_active_window_on_darwin(self) -> None:
    """Return details of the active window on macOS platform."""
    # TODO(xames3): Consider adding support for macOS builds.
    pass

  def _get_active_window_on_posix(self) -> Tuple[Optional[str], ...]:
    """Return details of the active window on linux platform."""
    # See https://stackoverflow.com/a/46640181 for more help.
    window, program = None, None
    # We use `xprop` to extract the properties of the root app
    # window, avoiding the need of unnecessary package installs.
    # Note that this method relies of `subprocess.Popen()` over
    # any other subprocess methods.
    # See https://stackoverflow.com/a/25703638 before updating
    # and/or optimizing the code.
    root = Popen(["xprop", "-root", "_NET_ACTIVE_WINDOW"], stdout=PIPE)
    # pyright: reportInvalidStringEscapeSequence=false
    window_id = re.search(b"^_NET_ACTIVE_WINDOW.* ([\w]+)$",
                          root.communicate()[0]).group(1)
    # Check if the window has loaded completely, `b"0x0"` indicates
    # the window is still loading.
    if window_id and window_id != b"0x0":
      window = Popen(["xprop", "-id", window_id, "WM_NAME"], stdout=PIPE)
      window = re.search(b"WM_NAME\(\w+\) = (?P<name>.+)$",
                         window.communicate()[0]).group("name").decode("utf-8")

      program = Popen(["xprop", "-id", window_id, "WM_CLASS"], stdout=PIPE)
      program = re.match(b"WM_CLASS\(\w+\) = (?P<name>.+)$",
                         program.communicate()[0]).group(
          "name").decode("utf-8")

      window = window.strip('"') if window else None
      program = program.split(", ")[1].strip('"') if program else None

    return window, program

  def _get_active_url_on_nt(self, program: str) -> Tuple[Optional[str], ...]:
    """Return details of the active url on windows platform."""
    # TODO(xames3): Add support for other browsers.
    if program != "Google Chrome":
      return None, None
    # See https://stackoverflow.com/a/59917905 for fetching URL
    # from current chrome tab and for fetching URL from current
    # firefox tab see this https://stackoverflow.com/a/2598682.
    # NOTE(xames3): Firefox method has not been tested yet.
    try:
      # pyright: reportGeneralTypeIssues=false
      self.uia.connect(title_re=".*Chrome.*", active_only=True)
      raw = self._uia.top_window()
      # TODO(xames3): This is not the right approach of saving
      # URLs. Add support for fetching url headers correctly.
      _url = "https://"
      _url += raw.child_window(title=self._title,
                               control_type="Edit").get_value()
      _domain = re.match(r"(.*://)?([^/?]+)./*", _url)[0]
      return _url, _domain
    except (pywinauto.findwindows.ElementNotFoundError, comtypes.COMError):
      # These are not true exceptions and are raised due to lack
      # of proper function call.
      pass
    except Exception as _error:
      self.log.exception(_error)
      return None, None

  def _get_active_url_on_darwin(self, program: str) -> Tuple:
    """Return details of the active url on macOS platform."""
    # TODO(xames3): Consider adding support for macOS builds.
    return None, None

  def _get_active_url_on_posix(self, program: str) -> Tuple:
    """Return details of the active url on linux platform."""
    # TODO(xames3): Consider adding support for Linux builds.
    return None, None

  def _unknown_os(self) -> Tuple[None, ...]:
    """Return tuple of None for unknown os."""
    self.log.error("Current OS is not supported.")
    return None, None

  def _unknown_url(self, program) -> Tuple[None, ...]:
    """Return tuple of None for unknown browsing programs."""
    self.log.error(f"URL tracking using {program} is not supported.")
    return None, None

  @property
  def activate(self) -> None:
    """Activate Baby Monitor Protocol."""
    self._window, self._program = None, None
    url, self._url, domain, self._domain = None, None, None, None
    self.log.info(f"{self._name} started tracking {USER}...")
    # We keep the protocol running irrespective of the exceptions.
    # This is ensured by suspending the service for 5 seconds and
    # getting it back up and running.
    while True:
      try:
        started = now()
        while True:
          window, program = self._active_window.get(self._os,
                                                    self._unknown_os)()
          # Check whether the window and program are available for
          # recording. We need to check this so that we do not add
          # null entries in the CSV data sheet. If both window and
          # the program are valid, we check if state of the window
          # has been changed. We ensure that entry for each of the
          # distinct window has been added just once. For the sake
          # of simplicity, we compare the active window title with
          # previously recorded title.
          if window and program and self._window != window:
            stopped = now()
            seconds_spent = (stopped - started).total_seconds()
            # We do not use the seconds spent on the first record
            # as it will always be 0 for it and the actual seconds
            # spent might be different and the following records
            # could become unreliable.
            if seconds_spent != 0:
              time_spent = seconds_to_datetime(seconds_spent).split(":")
              url, domain = self._active_url.get(self._os,
                                                 self._unknown_url)(program)
              try:
                self._csv.write(self._headers,
                                self._window,
                                self._program,
                                self._url,
                                self._domain,
                                started,
                                stopped,
                                seconds_spent,
                                *time_spent)
              except PermissionError:
                self.log.error("File is accessed by another program.")
              started = now()

            self._window = window
            self._program = program
            self._url = url
            self._domain = domain

          time.sleep(self._refresh)
      except KeyboardInterrupt:
        self.log.warning(f"{self._name} was interrupted.")
        sys.exit(0)
      except Exception as _error:
        self.log.exception(_error)
      finally:
        time.sleep(5.0)
