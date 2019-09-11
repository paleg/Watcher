#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, division, unicode_literals, absolute_import

import sys
import pyinotify
import string
import logging
import time
import re

from .eventhandler import EventHandler, get_stdout_log, process_report

def watcher(config):
    # for background processes polling
    processes = {}

    wdds      = dict()
    notifiers = dict()

    # read jobs from config file
    for section in config.sections():
        # mandatory opts
        mask      = parseMask(config.get(section, 'events').split(','))
        folder    = config.get(section, 'watch')
        command   = config.get(section, 'command')
        # optional opts (i.e. with default values)
        recursive = config.getboolean(section, 'recursive')
        autoadd   = config.getboolean(section, 'autoadd')
        excluded  = None if not config.get(section, 'excluded') else set(config.get(section, 'excluded').split(','))
        include_extensions = None if not config.get(section, 'include_extensions') else set(config.get(section, 'include_extensions').split(','))
        exclude_extensions = None if not config.get(section, 'exclude_extensions') else set(config.get(section, 'exclude_extensions').split(','))
        exclude_re = None if not config.get(section, 'exclude_re') else re.compile(config.get(section, 'exclude_re'))
        background = config.getboolean(section, 'background')
        log_output = config.getboolean(section, 'log_output')

        outfile = config.get(section, 'outfile')
        if outfile:
            t = string.Template(outfile)
            outfile = t.substitute(job=section)
            if log_output:
               logging.debug("logging '%s' output to '%s'", section, outfile)
        elif log_output:
            logging.debug("logging '%s' output to daemon log", section)

        action_on_success = config.get(section, 'action_on_success')
        action_on_failure = config.get(section, 'action_on_failure')

        logging.info("%s: watching '%s'", section, folder)

        wm = pyinotify.WatchManager()
        handler = EventHandler(processes,
                               job = section,
                               mask = mask,
                               folder = folder,
                               command = command,
                               log_output = log_output,
                               include_extensions = include_extensions,
                               exclude_extensions = exclude_extensions,
                               exclude_re = exclude_re,
                               background = background,
                               action_on_success = action_on_success,
                               action_on_failure = action_on_failure,
                               outfile = outfile
                              )

        wdds[section] = wm.add_watch(folder, mask, rec=recursive, auto_add=autoadd)
        # Remove watch about excluded dir.
        if excluded:
            for excluded_dir in excluded:
                for (k, v) in list(wdds[section].items()):
                    try:
                        if k.startswith(excluded_dir):
                            wm.rm_watch(v)
                            wdds[section].pop(k)
                    except UnicodeDecodeError:
                        logging.exception("Failed to check exclude for %r (decoding error)", k)
                logging.debug("Excluded dirs : %s", excluded_dir)
        # Create ThreadNotifier so that each job has its own thread
        notifiers[section] = pyinotify.ThreadedNotifier(wm, handler)
        notifiers[section].setName(section)

    # Start all the notifiers.
    for (name, notifier) in notifiers.items():
        try:
            notifier.start()
            logging.debug('Notifier for %s is instanciated', name)
        except pyinotify.NotifierError as err:
            logging.warning('%r %r', sys.stderr, err)

    # Wait for SIGTERM
    try:
        while 1:
            try:
                # build new list as we want to change dict on-fly
                for process in list(processes):
                    if process.poll() is not None:
                        stdoutdata = get_stdout_log(processes[process]['logHandler'])
                        process_report(process, processes[process]['opts'], stdoutdata)
                        del processes[process]
            except Exception as err:
                logging.exception("Failed to collect children:")
            time.sleep(0.1)
    except:
        cleanup_notifiers(notifiers)

def cleanup_notifiers(notifiers):
    """Close notifiers instances when the process is killed
    """
    for notifier in notifiers.values():
        notifier.stop()

def parseMask(masks):
    ret = False

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
