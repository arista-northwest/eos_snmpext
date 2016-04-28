#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (c) 2016 Arista Networks, Inc.  All rights reserved.
# Arista Networks, Inc. Confidential and Proprietary.

import argparse
import functools
import importlib
import os
import pkgutil
import re
import sys
import syslog
import time
import eos_snmpext.extensions
from eos_snmpext.contrib import snmp_passpersist
from eos_snmpext.util import memoize

# ====================
BASE_POLLING_INTERVAL = 1
MAX_RETRY = 10
BASE_OID = ".1.3.6.1.4.1.8072.1.3.1.5"
DEBUG = False
# search these paths for the 'snmpext' directory
PATHS = ['/mnt/flash', '/persist/local']
# ====================

PACKAGES = [eos_snmpext.extensions]
LAST_INTERVAL = {}

for path in PATHS:
    path = os.path.abspath(os.path.expanduser(path))

    if not os.path.exists(path):
        continue

    if path not in sys.path:
        sys.path.insert(1, path)

try:
    import snmpext
    PACKAGES.insert(0, snmpext)
except ImportError:
    pass

# See: https://mail.python.org/pipermail/tutor/2003-November/026645.html
class Unbuffered(object):
   def __init__(self, stream):
       self.stream = stream
   def write(self, data):
       self.stream.write(data)
       self.stream.flush()
   def __getattr__(self, attr):
       return getattr(self.stream, attr)

import sys
sys.stdout = Unbuffered(sys.stdout)
sys.stderr = Unbuffered(sys.stderr)

def log(msg):
    syslog.syslog(msg)
    if DEBUG:
        print msg

def _load_extensions(names):
    modules = []
    for package in PACKAGES:
        for importer, name, ispkg in pkgutil.iter_modules(package.__path__, ''):

            if names and name not in names:
                continue

            full_name = ".".join([package.__name__, name])
            module = importer.find_module(name).load_module(full_name)

            if not hasattr(module, 'update'):
                continue

            if not is_supported(module):
                log("%SNMPEXT-5-EXT_LOADED: Loaded '{}' snmp extension".format(name))
                continue

            modules.append(module)
    return modules

def is_supported(extension):
    supported = True

    if not hasattr(extension, 'supported'):
        return supported

    try:
        supported = extension.supported()
    except Exception as exc:
        log(("%SNMPEXT-5-EXT_FAILED: Extension '{}' failed to "
             "load: {}").format(extension.__name__, exc.message))
        supported = False

    if not supported:
        log(("%SNMPEXT-5-EXT_UNSUPPORTED: Extension '{}' is not supported on "
             "this platform").format(extension.__name__))

    return supported

def update(pp, extensions):
    polling_interval = 0
    last_interval = 0

    for ext in extensions:
        name = ext.__name__
        now = time.time()

        if hasattr(ext, 'POLLING_INTERVAL'):
            polling_interval = ext.POLLING_INTERVAL

        if hasattr(ext, '_LAST_INTERVAL'):
            last_interval = ext._LAST_INTERVAL

        if now - last_interval >= polling_interval:
            ext.update(pp)
            ext._LAST_INTERVAL = now

def main():
    global DEBUG

    parser = argparse.ArgumentParser(prog="arcomm")
    arg = parser.add_argument

    arg("extensions", nargs="*", default=[])
    arg("-d", "--debug", action="store_true", default=False, help="enable debugging")
    args = parser.parse_args()

    syslog.openlog('snmpext', 0, syslog.LOG_LOCAL4)

    DEBUG = args.debug
    extensions = _load_extensions(args.extensions)
    retry_counter = MAX_RETRY

    while retry_counter > 0:
        try:
            pp = snmp_passpersist.PassPersist(BASE_OID)
            func = functools.partial(update, pp, extensions)
            pp.start(func, BASE_POLLING_INTERVAL)
        except KeyboardInterrupt:
            log("%SNMPEXT-4-SHUTDOWN: {}".format("Exiting on user request"))
            sys.exit(0)
        except IOError as exc:
            if e.errno == errno.EPIPE:
                message = "snmpd has closed the pipe"
                log("%SNMPEXT-4-PIPE_CLOSED: {}".format(message))
                sys.exit(0)
            message = "updater thread has died: {}".format(exc.message)
        # except Exception as exc:
        #     message = "main thread has died: {}".format(str(exc))

        log("%SNMPEXT-4-RETRYING: {}".format(message))
        retry_counter -= 1

    log("%SNMPEXT-3-RETRYS_EXHAUSTED: too many retrys, exiting")
    sys.exit(0)

if __name__ == "__main__":
    main()