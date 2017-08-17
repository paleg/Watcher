#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, division, unicode_literals, absolute_import

import os
import logging
import time
import signal, errno
import daemon

from past.builtins import basestring # pip install future

try:
    from daemon.pidlockfile import PIDLockFile
    from daemon.pidlockfile import AlreadyLocked
except (NameError, ImportError):
    from lockfile.pidlockfile import PIDLockFile
    from lockfile import AlreadyLocked

class DaemonRunnerError(Exception):
    """ Abstract base class for errors from DaemonRunner. """

class DaemonRunnerInvalidActionError(ValueError, DaemonRunnerError):
    """ Raised when specified action for DaemonRunner is invalid. """

class DaemonRunnerStartFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure starting DaemonRunner. """

class DaemonRunnerStopFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure stopping DaemonRunner. """


class DaemonRunner(object):
    """ Controller for a callable running in a separate background process.

        * 'start': Become a daemon and call `run()`.
        * 'stop': Exit the daemon process specified in the PID file.
        * 'restart': Call `stop()`, then `start()`.
        * 'run': Run `func(func_arg)`
        """
    def __init__(self, func, func_arg=None,
                       pidfile=None,
                       stdin=None, stdout=None, stderr=None,
                       uid=None, gid=None, umask=None,
                       working_directory=None,
                       signal_map=None,
                       files_preserve=None):
        """ Set up the parameters of a new runner.

            The `func` argument is the function, with single argument `func_arg`, to daemonize.

            """
        self.func = func
        self.func_arg = func_arg
        self.daemon_context = daemon.DaemonContext(umask=umask or 0,
                                                   working_directory=working_directory or '/',
                                                   uid=uid, gid=gid)
        # python-daemon>=2.1 has initgroups=True by default but it requires root privs;
        # older versions don't support initgroups as constructor parameter so we set it manually instead:
        self.daemon_context.initgroups = False
        self.daemon_context.stdin  = open(stdin or '/dev/null', 'rb')
        self.daemon_context.stdout = open(stdout or '/dev/null', 'w+b')
        self.daemon_context.stderr = open(stderr or '/dev/null', 'w+b', buffering=0)

        self.pidfile = None
        if pidfile is not None:
            self.pidfile = make_pidlockfile(pidfile)
        self.daemon_context.pidfile = self.pidfile
        ## TO BE IMPLEMENTED
        if signal_map is not None:
            self.daemon_context.signal_map = signal_map
        self.daemon_context.files_preserve = files_preserve

    def restart(self):
        """ Stop, then start.
            """
        self.stop()
        self.start()

    def run(self):
        """ Run the application.
            """
        return self.func(self.func_arg)

    def start(self):
        """ Open the daemon context and run the application.
            """
        status = is_pidfile_stale(self.pidfile)
        if status == True:
            self.pidfile.break_lock()
        elif status == False:
            ## Allow only one instance of the daemon
            logging.info("Daemon already running with PID %r", self.pidfile.read_pid())
            return

        try:
            self.daemon_context.open()
        except AlreadyLocked:
            logging.info("PID file %r already locked", self.pidfile.path)
            return
        logging.info('Daemon started with pid %d', os.getpid())

        self.run()

    def stop(self):
        """ Exit the daemon process specified in the current PID file.
            """
        if not self.pidfile.is_locked():
            logging.info("PID file %r not locked", self.pidfile.path)
            return

        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            self._terminate_daemon_process()
            self.pidfile.break_lock()
        logging.info("Daemon stopped")

    def _terminate_daemon_process(self, sig=signal.SIGTERM):
        """ Terminate the daemon process specified in the current PID file.
            """
        pid = self.pidfile.read_pid()
        try:
            os.kill(pid, sig)
        except OSError as exc:
            raise DaemonRunnerStopFailureError(
                "Failed to terminate %(pid)d: %(exc)s" % vars())

        time.sleep(0.2)
        try:
            os.kill(pid, 0)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist
                logging.info("Pid %(pid)d terminated.", vars())
                return

        raise DaemonRunnerStopFailureError(
            "Failed to terminate %(pid)d" % vars())

def make_pidlockfile(path):
    """ Make a LockFile instance with the given filesystem path. """
    if not isinstance(path, basestring):
        raise ValueError("Not a filesystem path: %(path)r" % vars())
    if not os.path.isabs(path):
        raise ValueError("Not an absolute path: %(path)r" % vars())
    return PIDLockFile(path)

def is_pidfile_stale(pidfile):
    """ Determine whether a PID file is stale.

        Return ``True`` (“stale”) if the contents of the PID file are
        valid but do not match the PID of a currently-running process;
        otherwise return ``False``.

        """
    result = False
    if not os.path.isfile(pidfile.path):
        return None
    pidfile_pid = pidfile.read_pid()
    if pidfile_pid is not None:
        try:
            os.kill(pidfile_pid, signal.SIG_DFL)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist
                result = True

    return result
