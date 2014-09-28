# Copyright 2014 Dirk Pranke. All rights reserved.
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

import io
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib2


orig_stderr = sys.stderr
orig_stdout = sys.stdout


class Host(object):
    python_interpreter = sys.executable
    sep = os.sep
    stdin = sys.stdin
    stderr = sys.stderr
    stdout = sys.stdout
    orig_stderr = sys.stderr

    def abspath(self, *comps):
        return os.path.abspath(self.join(*comps))

    def add_to_path(self, *comps):
        absolute_path = self.abspath(*comps)
        if not absolute_path in sys.path:
            sys.path.append(absolute_path)

    def basename(self, path):
        return os.path.basename(path)

    def call(self, argv, stdin=None, env=None):
        if stdin:
            stdin_pipe = subprocess.PIPE
        else:
            stdin_pipe = None
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=stdin_pipe,
                                env=env)
        if stdin_pipe:
            proc.stdin.write(stdin)
        stdout, stderr = proc.communicate()
        return proc.returncode, stdout, stderr

    def chdir(self, *comps):
        return os.chdir(self.join(*comps))

    def cpu_count(self):
        return multiprocessing.cpu_count()

    def dirname(self, *comps):
        return os.path.dirname(self.join(*comps))

    def exists(self, *comps):
        return os.path.exists(self.join(*comps))

    def files_under(self, top):
        all_files = []
        for root, _, files in os.walk(top):
            for f in files:
                relpath = self.relpath(os.path.join(root, f), top)
                all_files.append(relpath)
        return all_files

    def getcwd(self):
        return os.getcwd()

    def getenv(self, key, default=None):
        return os.getenv(key, default=default)

    def for_mp(self):
        return None

    def isdir(self, *comps):
        return os.path.isdir(os.path.join(*comps))

    def isfile(self, *comps):
        return os.path.isfile(os.path.join(*comps))

    def join(self, *comps):
        return os.path.join(*comps)

    def maybe_mkdir(self, *comps):
        path = self.abspath(self.join(*comps))
        if not self.exists(path):
            os.mkdir(path)

    def mkdtemp(self, **kwargs):
        return tempfile.mkdtemp(**kwargs)

    def mtime(self, *comps):
        return os.stat(self.join(*comps)).st_mtime

    def print_(self, msg='', end='\n', stream=None):
        stream = stream or self.stdout
        stream.write(str(msg) + end)
        stream.flush()

    def read_text_file(self, *comps):
        return self._read(comps, 'r')

    def read_binary_file(self, *comps):
        return self._read(comps, 'rb')

    def _read(self, comps, mode):
        path = self.join(*comps)
        with open(path, mode) as f:
            return f.read()

    def relpath(self, path, start):
        return os.path.relpath(path, start)

    def remove(self, *comps):
        os.remove(self.join(*comps))

    def rmtree(self, path):
        shutil.rmtree(path, ignore_errors=True)

    def splitext(self, path):
        return os.path.splitext(path)

    def time(self):
        return time.time()

    def write_text_file(self, path, contents):
        return self._write(path, contents, mode='w')

    def write_binary_file(self, path, contents):
        return self._write(path, contents, mode='wb')

    def _write(self, path, contents, mode):
        with open(path, mode) as f:
            f.write(contents)

    def fetch(self, url, data=None, headers=None): # pragma: no cover
        return urllib2.urlopen(urllib2.Request(url, data, headers))

    def terminal_width(self):
        """Returns 0 if the width cannot be determined."""
        try:
            if sys.platform == 'win32': # pragma: no cover
                # From http://code.activestate.com/recipes/ \
                #   440694-determine-size-of-console-window-on-windows/
                from ctypes import windll, create_string_buffer

                STDERR_HANDLE = -12
                handle = windll.kernel32.GetStdHandle(STDERR_HANDLE)

                SCREEN_BUFFER_INFO_SZ = 22
                buf = create_string_buffer(SCREEN_BUFFER_INFO_SZ)

                if windll.kernel32.GetConsoleScreenBufferInfo(handle, buf):
                    import struct
                    fields = struct.unpack("hhhhHhhhhhh", buf.raw)
                    left = fields[5]
                    right = fields[7]

                    # Note that we return 1 less than the width since writing
                    # into the rightmost column automatically performs a
                    # line feed.
                    return right - left
                return 0
            else:
                import fcntl
                import struct
                import termios
                packed = fcntl.ioctl(self.stderr.fileno(),
                                    termios.TIOCGWINSZ, '\0' * 8)
                _, columns, _, _ = struct.unpack('HHHH', packed)
                return columns
        except Exception: # pragma: no cover
            # TODO: Figure out how to test this and make coverage see it.
            return 0

    def tap_stdio(self):
        self.stdout = sys.stdout = _TeedStream(self.stdout)
        self.stderr = sys.stderr = _TeedStream(self.stderr)

    def untap_stdio(self):
        if isinstance(self.stdout, _TeedStream):
            self.stdout = sys.stdout = self.stdout.stream
            self.stderr = sys.stderr = self.stderr.stream

    def start_capturing_stdio(self):
        if isinstance(self.stdout, _TeedStream):
            self.stdout.start_capturing()
            self.stderr.start_capturing()

    def stop_capturing_stdio(self):
        if isinstance(self.stdout, _TeedStream):
            out = self.stdout.stop_capturing()
            err = self.stderr.stop_capturing()
            return out, err
        else: # pragma: no cover
            # TODO: add a test for this and other trap hooks.
            return None, None


class _TeedStream(io.StringIO):
    def __init__(self, stream):
        super(_TeedStream, self).__init__()
        self.stream = stream
        self.trap = False

    def write(self, msg, *args, **kwargs): # pragma: no cover
        if self.trap:
            super(_TeedStream, self).write(unicode(msg), *args, **kwargs)
        else:
            self.stream.write(unicode(msg), *args, **kwargs)

    def flush(self): # pragma: no cover
        if self.trap:
            super(_TeedStream, self).flush()
        else:
            self.stream.flush()

    def start_capturing(self):
        self.truncate(0)
        self.trap = True

    def stop_capturing(self):
        self.trap = False
        msg = self.getvalue()
        self.truncate(0)
        return msg
