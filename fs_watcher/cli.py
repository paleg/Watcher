# -*- coding: utf-8 -*-
from __future__ import print_function, division, unicode_literals, absolute_import

import os
import sys
import logging
import argparse

from . import __version__
from .daemonrunner import DaemonRunner
from .watcher import watcher

try:
    import configparser
except ImportError:  # python 2 and configparser from pip not installed
    import ConfigParser as configparser

def init_daemon(cfg):
    """Convert config.defaults() OrderedDict to a `dict` to use in daemon initialization
    """
    #logfile = cfg.get('logfile', '/tmp/watcher.log')
    pidfile = cfg.get('pidfile', '/tmp/watcher.pid')
    # uid
    uid = cfg.get('uid', None)
    if uid is not None:
        try:
            uid = int(uid)
        except ValueError as err:
            if uid != '':
                logging.warning('Incorrect uid value: %r', err)
            uid = None
    # gid
    gid = cfg.get('gid', None)
    if gid is not None:
        try:
            gid = int(gid)
        except ValueError as err:
            if gid != '':
                logging.warning('Incorrect gid value: %r', err)
            gid = None

    umask = cfg.get('umask', None)
    if umask is not None:
        try:
            umask = int(umask)
        except ValueError as err:
            if umask != '':
                logging.warning('Incorrect umask value: %r', err)
            umask = None

    workdir = cfg.get('working_directory', None)
    if workdir is not None and not os.path.isdir(workdir):
        if workdir != '':
            logging.warning('Working directory is not a valid directory ("%s"). Set to default ("/")', workdir)
        workdir = None

    return {'pidfile': pidfile,
            'stdin': None, 'stdout': None, 'stderr': None,
            'uid': uid, 'gid': gid, 'umask': umask,
            'working_directory': workdir}

def main():
    # Parse commandline arguments
    parser = argparse.ArgumentParser(description='A daemon to monitor changes within specified directories and run commands on these changes.')
    parser.add_argument('--version', action='version', version="%(prog)s {}".format(__version__))
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
    config = configparser.ConfigParser({'recursive': "true",
                                        'autoadd': "true",
                                        'excluded': None,
                                        'include_extensions': None,
                                        'exclude_extensions': None,
                                        'exclude_re': None,
                                        'background': "false",
                                        'log_output': "true",
                                        'action_on_success': None,
                                        'action_on_failure': None,
                                        'outfile': None
                                       }, allow_no_value=True)
    if args.config:
        # load config file specified by commandline
        confok = config.read(args.config)
    else:
        # load config file from default locations
        confok = config.read(['/etc/watcher.ini', os.path.expanduser('~/.watcher.ini')])
    if not confok:
        sys.stderr.write("Failed to read config file. Try -c parameter\n")
        sys.exit(4)

    # Initialize logging
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logformatter       = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logformatter_debug = logging.Formatter("%(asctime)s - %(levelname)s - %(threadName)s - %(funcName)s:%(lineno)d - %(message)s")

    if args.command == 'debug':
        loghandler = logging.StreamHandler()
        logger.setLevel(logging.DEBUG)
    else:
        loghandler = logging.FileHandler(config.get('DEFAULT', 'logfile'))
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    if logger.getEffectiveLevel() <= logging.DEBUG:
        loghandler.setFormatter(logformatter_debug)
    else:
        loghandler.setFormatter(logformatter)
    logger.addHandler(loghandler)
    logging.getLogger("chardet.charsetprober").setLevel(logging.CRITICAL)

    # Initialize the daemon
    options = init_daemon(config.defaults())
    options['files_preserve'] = [loghandler.stream]
    options['func_arg'] = config
    daemon = DaemonRunner(watcher, **options)

    # Execute the command
    if args.command == 'start':
        daemon.start()
        #logging.info('Daemon started')
    elif args.command == 'stop':
        daemon.stop()
        #logging.info('Daemon stopped')
    elif args.command == 'restart':
        daemon.restart()
        #logging.info('Daemon restarted')
    elif args.command == 'debug':
        logging.warning('Press Control+C to quit...')
        daemon.run()
        #logging.info('Debug mode')
    else:
        print("Unknown Command")
        sys.exit(2)
    sys.exit(0)

if __name__ == '__main__':
    main()
