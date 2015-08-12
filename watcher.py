#!/usr/bin/python
# -*- coding: utf-8 -*-

##/usr/bin/env python
##
##  Author: Bertrand Lacoste
##  Modified from daemon.runner and from watcher (https://github.com/splitbrain/Watcher, original work https://github.com/gregghz/Watcher)
##

import sys, os, grp
import datetime, signal, errno
import pyinotify
import argparse, ConfigParser, string
import logging, time
import daemon
try:
    from daemon import pidlockfile
except ImportError:
    from daemon import pidfile as pidlockfile
import re
import subprocess
import shlex


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
    def __init__(self, func, func_arg=None, pidfile=None, stdin=None, stdout=None, stderr=None, uid=None, gid=None, umask=None, working_directory=None, signal_map=None, files_preserve=None):
        """ Set up the parameters of a new runner.

            The `func` argument is the function, with single argument `func_arg`, to daemonize.

            """
        self.func = func
        self.func_arg = func_arg
        self.daemon_context = daemon.DaemonContext(umask=umask or 0,
                            working_directory=working_directory or '/',
                            uid=uid, gid=gid)
        self.daemon_context.stdin  = open(stdin or '/dev/null', 'r')
        self.daemon_context.stdout = open(stdout or '/dev/null', 'w+')
        self.daemon_context.stderr = open(stderr or '/dev/null', 'w+', buffering=0)

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
            pid = self.pidfile.read_pid()
            logger.info("Daemon already running with PID %(pid)r" % vars())
            return
            
        try:
            self.daemon_context.open()
        except pidlockfile.AlreadyLocked:
            pidfile_path = self.pidfile.path
            logger.info("PID file %(pidfile_path)r already locked" % vars())
            return
        pid = os.getpid()
        logger.info('Daemon started with pid %(pid)d' % vars())

        self.run()

    def stop(self):
        """ Exit the daemon process specified in the current PID file.
            """
        if not self.pidfile.is_locked():
            pidfile_path = self.pidfile.path
            logger.info("PID file %(pidfile_path)r not locked" % vars())
            return
            
        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            self._terminate_daemon_process()
            self.pidfile.break_lock()
        logger.info("Daemon stopped")

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
                logger.info("Pid %(pid)d terminated." % vars())
                return

        raise DaemonRunnerStopFailureError(
            "Failed to terminate %(pid)d" % vars())
        
def make_pidlockfile(path):
    """ Make a PIDLockFile instance with the given filesystem path. """
    if not isinstance(path, basestring):
        error = ValueError("Not a filesystem path: %(path)r" % vars())
        raise error
    if not os.path.isabs(path):
        error = ValueError("Not an absolute path: %(path)r" % vars())
        raise error
    return pidlockfile.PIDLockFile(path)

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
        except OSError, exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist
                result = True

    return result

class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, job, folder, command, log_output, include_extensions, exclude_extensions, exclude_re, background, outfile):
        pyinotify.ProcessEvent.__init__(self)
        self.job = job
        self.folder = folder
        self.command = command
        self.include_extensions = include_extensions
        self.exclude_extensions = exclude_extensions
        self.exclude_re_txt = exclude_re
        self.exclude_re = None if not exclude_re else re.compile(exclude_re)
        self.background = background
        self.log_output = log_output
        if self.log_output:
            self.outfile = outfile if outfile else subprocess.PIPE
        else:
            self.outfile = None
        
    # from http://stackoverflow.com/questions/35817/how-to-escape-os-system-calls-in-python
    def shellquote(self,s):
        s = str(s)
        return "'" + s.replace("'", "'\\''") + "'"

    def runCommand(self, event):
        # if specified, exclude extensions, or include extensions.
        if self.include_extensions and all(not event.pathname.endswith(ext) for ext in self.include_extensions):
            #print "File %s excluded because its exension is not in the included extensions %r"%(event.pathname, self.include_extensions)
            logger.debug("File %s excluded because its extension is not in the included extensions %r"%(event.pathname, self.include_extensions))
            return
        if self.exclude_extensions and any(event.pathname.endswith(ext) for ext in self.exclude_extensions):
            #print "File %s excluded because its extension is in the excluded extensions %r"%(event.pathname, self.exclude_extensions)
            logger.debug("File %s excluded because its extension is in the excluded extensions %r"%(event.pathname, self.exclude_extensions))
            return
        if self.exclude_re and self.exclude_re.search(os.path.basename(event.pathname)):
            logger.debug("File %s excluded because its name matched exclude regexp '%s'"%(event.pathname, self.exclude_re_txt))
            return

        t = string.Template(self.command)
        command = t.substitute(job=self.shellquote(self.job),
                               folder=self.shellquote(self.folder),
                               watched=self.shellquote(event.path),
                               filename=self.shellquote(event.pathname),
                               tflags=self.shellquote(event.maskname),
                               nflags=self.shellquote(event.mask),
                               cookie=self.shellquote(event.cookie if hasattr(event, "cookie") else 0))
        try:
            args = shlex.split(command)
            if not self.background:
                # sync exec
                logger.info("Running command: '{0}'".format(command))
                process = subprocess.Popen(args, stdout=self.outfile, stderr=subprocess.STDOUT)
                output, code = process.communicate()
                if process.returncode == 0:
                    logger.info("Command finished successfully")
                else:
                    logger.info("Command failed, return code was {0}".format(process.returncode))
                if self.log_output and output:
                    logger.info("Output was: '{0}'".format(output))
            else:
                # async exec
                process = subprocess.Popen(args, stdout=self.outfile, stderr=subprocess.STDOUT)
                logger.info("Executed child ({0}): '{1}'".format(process.pid, command))
                processes.append( process )
        except OSError, err:
            #print "Failed to run command '%s' %s" % (command, str(err))
            logger.info("Failed to run command '%s' %s" % (command, str(err)))




    def process_IN_ACCESS(self, event):
        #print "Access: %s"%(event.pathname)
        logger.info("Access: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_ATTRIB(self, event):
        #print "Attrib: %s"%(event.pathname)
        logger.info("Attrib: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CLOSE_WRITE(self, event):
        #print "Close write: %s"%(event.pathname)
        logger.info("Close write: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CLOSE_NOWRITE(self, event):
        #print "Close nowrite: %s"%(event.pathname)
        logger.info("Close nowrite: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_CREATE(self, event):
        #print "Creating: %s"%(event.pathname)
        logger.info("Creating: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_DELETE(self, event):
        #print "Deleting: %s"%(event.pathname)
        logger.info("Deleting: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MODIFY(self, event):
        #print "Modify: %s"%(event.pathname)
        logger.info("Modify: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVE_SELF(self, event):
        #print "Move self: %s"%(event.pathname)
        logger.info("Move self: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVED_FROM(self, event):
        #print "Moved from: %s"%(event.pathname)
        logger.info("Moved from: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_MOVED_TO(self, event):
        #print "Moved to: %s"%(event.pathname)
        logger.info("Moved to: %s"%(event.pathname))
        self.runCommand(event)

    def process_IN_OPEN(self, event):
        #print "Opened: %s"%(event.pathname)
        logger.info("Opened: %s"%(event.pathname))
        self.runCommand(event)

def watcher(config):
    wdds      = dict()
    notifiers = dict()

    # read jobs from config file
    for section in config.sections():
        # get the basic config info
        mask      = parseMask(config.get(section, 'events').split(','))
        folder    = config.get(section, 'watch')
        recursive = config.getboolean(section, 'recursive')
        autoadd   = config.getboolean(section, 'autoadd')
        excluded  = None if '' in config.get(section, 'excluded').split(',') else set(config.get(section, 'excluded').split(','))
        include_extensions = None if '' in config.get(section, 'include_extensions').split(',') else set(config.get(section, 'include_extensions').split(','))
        exclude_extensions = None if '' in config.get(section, 'exclude_extensions').split(',') else set(config.get(section, 'exclude_extensions').split(','))
        command   = config.get(section, 'command')

        try:
            exclude_re = None if not config.get(section, 'exclude_re') else config.get(section, 'exclude_re')
        except ConfigParser.NoOptionError:
            exclude_re = None

        try:
            background = config.getboolean(section, 'background')
        except (ConfigParser.NoOptionError, ValueError):
            background = False

        try:
            log_output = config.getboolean(section, 'log_output')
        except (ConfigParser.NoOptionError, ValueError):
            log_output = True

        outfile = ''
        outfile_h = None
        if log_output:
            try:
                outfile = config.get(section, 'outfile')
            except ConfigParser.NoOptionError:
                pass
            if outfile:
                t = string.Template(outfile)
                outfile = t.substitute(job=section)
                logger.debug("logging '{0}' output to '{1}'".format(section, outfile))
                outfile_h = open(outfile, 'a+b', buffering=0)
            else:
                logger.debug("logging '{0}' output to daemon log".format(section))

        logger.info(section + ": " + folder)

        wm = pyinotify.WatchManager()
        handler = EventHandler(section, folder, command, log_output, include_extensions, exclude_extensions, exclude_re, background, outfile_h)

        wdds[section] = wm.add_watch(folder, mask, rec=recursive, auto_add=autoadd)
        # Remove watch about excluded dir. 
        if excluded:
            for excluded_dir in excluded :
                for (k,v) in wdds[section].items():
                    if k.startswith(excluded_dir):
                        wm.rm_watch(v)
                        wdds[section].pop(k)
                logger.debug("Excluded dirs : " + excluded_dir)
        # Create ThreadNotifier so that each job has its own thread
        notifiers[section] = pyinotify.ThreadedNotifier(wm, handler)

    # Start all the notifiers.
    for (name,notifier) in notifiers.iteritems():
        try:
            notifier.start()
            logger.debug('Notifier for %s is instanciated'%(name))
        except pyinotify.NotifierError as err:
            logger.warning( '%r %r'%(sys.stderr, err))
    
    # Wait for SIGTERM
    try:
        while 1:
            for process in list(processes):
                if process.poll():
                    if process.returncode == 0:
                        logger.info("Child {0} finished successfully".format(process.pid))
                    else:
                        logger.error("Child {0} failed, return code was {1}".format(process.pid, process.returncode))
                    if process.stdout:
                        output = process.stdout.read()
                        if output:
                            logger.info("Output was: '{0}'".format(output))

                    processes.remove( process )
            time.sleep(0.1)
    except:
        cleanup_notifiers(notifiers)
    if outfile:
        outfile_h.close()
        logger.debug("closed %s"%outfile)
    
def cleanup_notifiers(notifiers):
    """Close notifiers instances when the process is killed
    """
    for notifier in notifiers.values():
        notifier.stop()

def parseMask(masks):
    ret = False;

    for mask in masks:
        mask = mask.strip()

        if 'access' == mask:
            ret = addMask(pyinotify.IN_ACCESS, ret)
        elif 'attribute_change' == mask:
            ret = addMask(pyinotify.IN_ATTRIB, ret)
        elif 'write_close' == mask:
            ret = addMask(pyinotify.IN_CLOSE_WRITE, ret)
        elif 'nowrite_close' == mask:
            ret = addMask(pyinotify.IN_CLOSE_NOWRITE, ret)
        elif 'create' == mask:
            ret = addMask(pyinotify.IN_CREATE, ret)
        elif 'delete' == mask:
            ret = addMask(pyinotify.IN_DELETE, ret)
        elif 'self_delete' == mask:
            ret = addMask(pyinotify.IN_DELETE_SELF, ret)
        elif 'modify' == mask:
            ret = addMask(pyinotify.IN_MODIFY, ret)
        elif 'self_move' == mask:
            ret = addMask(pyinotify.IN_MOVE_SELF, ret)
        elif 'move_from' == mask:
            ret = addMask(pyinotify.IN_MOVED_FROM, ret)
        elif 'move_to' == mask:
            ret = addMask(pyinotify.IN_MOVED_TO, ret)
        elif 'open' == mask:
            ret = addMask(pyinotify.IN_OPEN, ret)
        elif 'all' == mask:
            m = pyinotify.IN_ACCESS | pyinotify.IN_ATTRIB | pyinotify.IN_CLOSE_WRITE | \
                pyinotify.IN_CLOSE_NOWRITE | pyinotify.IN_CREATE | pyinotify.IN_DELETE | \
                pyinotify.IN_DELETE_SELF | pyinotify.IN_MODIFY | pyinotify.IN_MOVE_SELF | \
                pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO | pyinotify.IN_OPEN
            ret = addMask(m, ret)
        elif 'move' == mask:
            ret = addMask(pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO, ret)
        elif 'close' == mask:
            ret = addMask(pyinotify.IN_CLOSE_WRITE | pyinotify.IN_CLOSE_NOWRITE, ret)
    return ret

def addMask(new_option, current_options):
    if not current_options:
        return new_option
    else:
        return current_options | new_option

def init_daemon(cf):
    """Convert config.defaults() OrderedDict to a `dict` to use in daemon initialization
    """
    #logfile = cf.get('logfile', '/tmp/watcher.log')
    pidfile = cf.get('pidfile', '/tmp/watcher.pid')
    # uid
    uid = cf.get('uid', None)
    if uid is not None:
        try:
            uid = int(uid)
        except ValueError as e:
            if uid != '':
                logger.warning('Incorrect uid value: %r' %(e))    
            uid = None
    # gid
    gid = cf.get('gid', None)
    if gid is not None:
        try:
            gid = int(gid)
        except ValueError as e:
            if gid != '':
                logger.warning('Incorrect gid value: %r' %(e))    
            gid = None

    umask = cf.get('umask', None)
    if umask is not None:
        try:
            umask = int(umask)
        except ValueError as e:
            if umask != '':
                logger.warning('Incorrect umask value: %r' %(e))    
            umask = None

    wd = cf.get('working_directory', None)
    if wd is not None and not os.path.isdir(wd):
        if wd != '':
            logger.warning('Working directory not a valid directory ("%s"). Set to default ("/")' %(wd))    
        wd = None

    return {'pidfile':pidfile, 'stdin':None, 'stdout':None, 'stderr':None, 'uid':uid, 'gid':gid, 'umask':umask, 'working_directory':wd}

if __name__ == "__main__":
    # Parse commandline arguments
    parser = argparse.ArgumentParser(
                description='A daemon to monitor changes within specified directories and run commands on these changes.',
             )
    parser.add_argument('-c', '--config',
                        action='store',
                        help='Path to the config file (default: %(default)s)')
    parser.add_argument('command',
                        action='store',
                        choices=['start', 'stop', 'restart', 'debug'],
                        help='What to do.')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')

    args = parser.parse_args()

    # Parse the config file
    config = ConfigParser.ConfigParser()
    if args.config:
        # load config file specified by commandline
        confok = config.read(args.config)
    else:
        # load config file from default locations
        confok = config.read(['/etc/watcher.ini', os.path.expanduser('~/.watcher.ini')]);
    if not confok:
        sys.stderr.write("Failed to read config file. Try -c parameter\n")
        sys.exit(4);

    # Initialize logging
    logger = logging.getLogger("daemonlog")
    logger.setLevel(logging.INFO)
    logformatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    if args.command == 'debug':
        loghandler = logging.StreamHandler()
        logger.setLevel(logging.DEBUG)
    else: 
        loghandler = logging.FileHandler(config.get('DEFAULT', 'logfile'))
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    loghandler.setFormatter(logformatter)
    logger.addHandler(loghandler)

    # Initialize the daemon
    options = init_daemon(config.defaults())
    options['files_preserve'] = [loghandler.stream]
    options['func_arg'] = config
    daemon = DaemonRunner(watcher, **options)
    # for background processes polling
    processes = []
    
    # Execute the command
    if 'start' == args.command:
        daemon.start()
        #logger.info('Daemon started')
    elif 'stop' == args.command:
        daemon.stop()
        #logger.info('Daemon stopped')
    elif 'restart' == args.command:
        daemon.restart()
        #logger.info('Daemon restarted')
    elif 'debug' == args.command:
        logger.warning('Press Control+C to quit...')
        daemon.run()
        #logger.info('Debug mode')
    else:
        print "Unkown Command"
        sys.exit(2)
    sys.exit(0)
