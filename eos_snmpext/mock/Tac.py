# Copyright (c) 2020 Arista Networks, Inc.  All rights reserved.
# Arista Networks, Inc. Confidential and Proprietary.

class _MockInterface():
    def __init__(self):
        self.syslogFacility = None

def singleton(mod):
    return _MockInterface()
