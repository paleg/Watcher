#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function, division, unicode_literals, absolute_import

import os
import pyinotify
import string
import logging
import subprocess
import shlex
import socket
import chardet

from past.builtins import basestring # pip install future

from tempfile import NamedTemporaryFile

class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, processes, **opts):
        pyinotify.ProcessEvent.__init__(self)
        self.processes = processes
        self.opts = opts

    def runCommand(self, event):
        # if specified, exclude extensions, or include extensions.
        if self.opts['include_extensions'] and all(not event.pathname.endswith(ext) for ext in self.opts['include_extensions']):
            logging.debug("File '%s' excluded because its extension is not in the included extensions %r", event.pathname, self.opts['include_extensions'])
            return
        if self.opts['exclude_extensions'] and any(event.pathname.endswith(ext) for ext in self.opts['exclude_extensions']):
            logging.debug("File '%s' excluded because its extension is in the excluded extensions %r", event.pathname, self.opts['exclude_extensions'])
            return
        if self.opts['exclude_re'] and self.opts['exclude_re'].search(os.path.basename(event.pathname)):
            logging.debug("File '%s' excluded because its name matched exclude regexp '%s'", event.pathname, self.opts['exclude_re'].pattern)
            return

        try:
            t = string.Template(self.opts['command'])
            command = t.substitute(job=shellquote(self.opts['job']),
                                   folder=shellquote(self.opts['folder']),
                                   watched=shellquote(event.path),
                                   filename=shellquote(event.pathname),
                                   tflags=shellquote(event.maskname),
                                   nflags=shellquote(event.mask),
                                   cookie=shellquote(event.cookie if hasattr(event, "cookie") else 0))
        except Exception:
            logging.exception("Failed to substitute template '%s':", self.opts['command'])
            return

        try:
            logHandler = NamedTemporaryFile(prefix="watcher-", suffix=".log")

            args = shlex.split(command)
            if not self.opts['background']:
                # sync exec
                logging.info("Running command: '%s', temp log file: '%s'", command, logHandler.name)
                process = subprocess.Popen(args, stdout=logHandler, stderr=subprocess.STDOUT)
                process.communicate()
                stdoutdata = get_stdout_log(logHandler)
                process_report(process, self.opts, stdoutdata)
            else:
                # async exec
                process = subprocess.Popen(args, stdout=logHandler, stderr=subprocess.STDOUT)
                logging.info("Executed child (%s): '%s', temp log file: '%s'", process.pid, command, logHandler.name)
                self.processes[process] = { 'opts': self.opts, 'logHandler': logHandler }
        except Exception:
            logging.exception("Failed to run command '%s':", command)

    def process_IN_ACCESS(self, event):
        #print "Access: %s"%(event.pathname)
        logging.info("Access: %s", event.pathname)
        self.runCommand(event)

    def process_IN_ATTRIB(self, event):
        #print "Attrib: %s"%(event.pathname)
        logging.info("Attrib: %s", event.pathname)
        self.runCommand(event)

    def process_IN_CLOSE_WRITE(self, event):
        #print "Close write: %s"%(event.pathname)
        logging.info("Close write: %s", event.pathname)
        self.runCommand(event)

    def process_IN_CLOSE_NOWRITE(self, event):
        #print "Close nowrite: %s"%(event.pathname)
        logging.info("Close nowrite: %s", event.pathname)
        self.runCommand(event)

    def process_IN_CREATE(self, event):
        #print "Creating: %s"%(event.pathname)
        if not self.opts['mask'] & pyinotify.IN_CREATE:
            # pyinotify adds IN_CREATE to watch mask if auto_add is True
            # so we need to filter it manually here
            logging.debug("Skipping IN_CREATE as it was not defined in events")
            return
        logging.info("Creating: %s", event.pathname)
        self.runCommand(event)

    def process_IN_DELETE(self, event):
        #print "Deleting: %s"%(event.pathname)
        logging.info("Deleting: %s", event.pathname)
        self.runCommand(event)

    def process_IN_MODIFY(self, event):
        #print "Modify: %s"%(event.pathname)
        logging.info("Modify: %s", event.pathname)
        self.runCommand(event)

    def process_IN_MOVE_SELF(self, event):
        #print "Move self: %s"%(event.pathname)
        logging.info("Move self: %s", event.pathname)
        self.runCommand(event)

    def process_IN_MOVED_FROM(self, event):
        #print "Moved from: %s"%(event.pathname)
        logging.info("Moved from: %s", event.pathname)
        self.runCommand(event)

    def process_IN_MOVED_TO(self, event):
        #print "Moved to: %s"%(event.pathname)
        logging.info("Moved to: %s", event.pathname)
        self.runCommand(event)

    def process_IN_OPEN(self, event):
        #print "Opened: %s"%(event.pathname)
        logging.info("Opened: %s", event.pathname)
        self.runCommand(event)


# from http://stackoverflow.com/questions/35817/how-to-escape-os-system-calls-in-python
def shellquote(s):
    # prevent converting unicode to str on python2 (causes UnicodeEncodeError)
    if not isinstance(s, basestring):
        s = str(s)
    return "'" + s.replace("'", "'\\''") + "'"

def post_action(cmd, job, output):
    if not cmd: return

    try:
        # convert output to unicode
        enc = chardet.detect(output)['encoding']
        if enc is not None:
            output = output.decode(enc)
    except Exception as err:
        logging.exception("Failed to convert output:")
        output = "unparsable output"

    try:
        t = string.Template(cmd)
        command = t.substitute(job=shellquote(job),
                               host=shellquote(socket.gethostname()),
                               output=shellquote(output))
    except Exception:
        logging.exception("Failed to substitute post cmd '%s':", cmd)
        return

    try:
        output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell = True)
        logging.debug("post action succeed: '%s'", output)
    except subprocess.CalledProcessError as err:
        logging.error("post action failed, return code was %s: '%s'", err.returncode, err.output)

def process_report(process, opts, stdoutdata):
    prefix = "Child {0}".format(process.pid) if opts['background'] else "Command"
    if process.returncode == 0:
        post_action(opts['action_on_success'], opts['job'], stdoutdata)
        msg = "{0} finished successfully".format(prefix)
    else:
        post_action(opts['action_on_failure'], opts['job'], stdoutdata)
        msg = "{0} failed, return code was {1}".format(prefix, process.returncode)
    logging.info(msg)

    if opts['log_output']:
        if opts['outfile']:
            with open(opts['outfile'], 'a+b') as fh:
                fh.write(stdoutdata)
        else:
            try:
                enc = chardet.detect(stdoutdata)['encoding']
                stdoutdata = stdoutdata.decode(enc)
            except Exception as err:
                pass
            logging.info("Output was: '%s'", stdoutdata)

def get_stdout_log(logHandler):
    try:
        logHandler.seek(0)
        stdoutdata = logHandler.read()
        logHandler.close()
    except Exception:
        logging.exception("Failed to get stdout log")
        # use encode to be compatible with python3
        stdoutdata = "".encode()
    return stdoutdata
