# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import sys
import unittest

from typ.host import Host
from typ.runner import Runner

def main(argv=None, host=None, loader=None):
    runner = make_runner(host=host, loader=loader)
    return runner.main(argv)


def make_runner(host=None, loader=None):
    host = host or Host()
    loader = loader or unittest.loader.TestLoader()
    return Runner(host, loader)


def spawn_main(): # pragma: no cover
    # This function is called from __main__.py when running
    # 'python -m typ' on windows: in order to use multiprocessing on windows,
    # we need to ensure that the 'main' module is importable,
    # and __main__.py isn't.
    # This code instead spawns a subprocess and invokes tester.py directly;
    # We don't want to always spawn a subprocess, because that is more
    # heavyweight than it needs to be on other platforms.
    proc = subprocess.Popen([sys.executable, __file__] + sys.argv[1:])
    try:
        proc.wait()
    except KeyboardInterrupt:
        # We may need a second wait in order to make sure the subprocess exits
        # completely.
        proc.wait()
    return proc.returncode


if __name__ == '__main__': # pragma: no cover
    sys.exit(main())
