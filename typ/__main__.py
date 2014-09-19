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

import os
import sys


def main():
    if sys.platform == 'win32':
        # In order to use multiprocessing on windows, we need to ensure
        # that the 'main' module is importable, and __main__.py isn't.
        # This code instead spawns a subprocess and invokes the main routine
        # in tester.py, which *is* importable.
        typ_dir = os.path.dirname(os.path.abspath(__file__))
        tester_path = os.path.join(typ_dir, 'tester.py')
        import subprocess
        proc = subprocess.Popen([sys.executable, tester_path] + sys.argv[1:])
        try:
            proc.wait()
        except KeyboardInterrupt:
            # We need a second wait in order to make sure the subprocess exits
            # completely.
            proc.wait()
        return proc.returncode
    else:
        from typ import tester
        return tester.main()


if __name__ == '__main__':
    sys.exit(main())
