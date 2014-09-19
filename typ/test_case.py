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
import tempfile
import unittest

from typ import host as typ_host


class MainTestCase(unittest.TestCase):
    prog = None
    host = None

    def _write_files(self, host, files):
        for path, contents in list(files.items()):
            dirname = host.dirname(path)
            if dirname:
                host.maybe_mkdir(dirname)
            host.write(path, contents)

    def _read_files(self, host, tmpdir):
        out_files = {}
        for f in host.files_under(tmpdir):
            out_files[f] = host.read(tmpdir, f)
        return out_files

    def assert_files(self, expected_files, actual_files):
        for k, v in expected_files.items():
            self.assertEqual(expected_files[k], v)
        interesting_files = set(actual_files.keys()).difference(
            self._files_to_ignore())
        self.assertEqual(interesting_files, set(expected_files.keys()))

    def make_host(self):
        return typ_host.Host()

    def call(self, host, argv, stdin, env):
        return host.call(argv, stdin=stdin, env=env)

    def check(self, cmd=None, argv=None, stdin=None, stdout=None, stderr=None, env=None,
              files=None, prog=None, cwd=None, host=None,
              exp_exit=None, exp_stdout=None, exp_stderr=None, exp_files=None):
        prog = prog or self.prog
        host = host or self.host or self.make_host()
        stdin_io = StringIO(stdin) if stdin else None

        if argv is None:
            # FIXME: Need something smarter here
            argv = cmd.split() if cmd else []

        try:
            orig_wd = host.getcwd()
            tmpdir = host.mkdtemp()
            host.chdir(tmpdir)
            if files:
                self._write_files(host, files)
            if cwd:
                host.chdir(cwd)

            result = self.call(host, prog + argv, stdin=stdin_io, env=env)

            actual_exit, actual_stdout, actual_stderr = result
            actual_files = self._read_files(host, tmpdir)
        finally:
            host.rmtree(tmpdir)
            host.chdir(orig_wd)

        if exp_exit is not None:
            self.assertEqual(actual_exit, exp_exit)
        if exp_stdout is not None:
            self.assertEqual(actual_stdout, exp_stdout)
        if exp_stderr is not None:
            self.assertEqual(actual_stderr, exp_stderr)
        if exp_files:
            self.assert_files(exp_files, actual_files)

        return actual_exit, actual_stdout, actual_stderr, actual_files
