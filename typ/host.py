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

import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import time


class Host(object):
    stderr = sys.stderr
    stdout = sys.stdout
    python_interpreter = sys.executable

    def abspath(self, *comps):
        return os.path.abspath(self.join(*comps))

    def call(self, argv, stdin=None, env=None):
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=stdin, env=env)
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

    def print_err(self, msg, end='\n'):
        self.stderr.write(str(msg) + end)

    def print_out(self, msg, end='\n'):
        self.stdout.write(str(msg) + end)
        self.stdout.flush()

    def read(self, *comps):
        path = self.join(*comps)
        with open(path) as f:
            return f.read()

    def relpath(self, path, start):
        return os.path.relpath(path, start)

    def remove(self, *comps):
        os.remove(self.join(*comps))

    def rmtree(self, path):
        shutil.rmtree(path, ignore_errors=True)

    def time(self):
        return time.time()

    def write(self, path, contents):
        with open(path, 'w') as f:
            f.write(contents)
