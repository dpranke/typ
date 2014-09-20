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

import shlex
import unittest

from typ import host as typ_host


class TestCase(unittest.TestCase):
    typ_context = None


class MainTestCase(TestCase):
    prog = None
    host = None

    def _write_files(self, host, files):
        for path, contents in list(files.items()):
            dirname = host.dirname(path)
            if dirname:
                host.maybe_mkdir(dirname)
            host.write_binary_file(path, contents)

    def _read_files(self, host, tmpdir):
        out_files = {}
        for f in host.files_under(tmpdir):
            out_files[f] = host.read_binary_file(tmpdir, f)
        return out_files

    def assert_files(self, expected_files, actual_files, files_to_ignore=None):
        files_to_ignore = files_to_ignore or []
        for k, v in expected_files.items():
            self.assertEqual(expected_files[k], v)
        interesting_files = set(actual_files.keys()).difference(
            files_to_ignore)
        self.assertEqual(interesting_files, set(expected_files.keys()))

    def make_host(self):
        return typ_host.Host()

    def call(self, host, argv, stdin, env):
        return host.call(argv, stdin=stdin, env=env)

    def check(self, cmd=None, stdin=None, env=None, files=None,
              prog=None, cwd=None, host=None,
              ret=None, out=None, err=None, exp_files=None,
              files_to_ignore=None):
        # Too many arguments pylint: disable=R0913
        prog = prog or self.prog
        host = host or self.host or self.make_host()
        argv = shlex.split(cmd) if isinstance(cmd, basestring) else cmd or []

        tmpdir = None
        orig_wd = host.getcwd()
        try:
            tmpdir = host.mkdtemp()
            host.chdir(tmpdir)
            if files:
                self._write_files(host, files)
            if cwd:
                host.chdir(cwd)

            result = self.call(host, prog + argv, stdin=stdin, env=env)

            actual_ret, actual_out, actual_err = result
            actual_files = self._read_files(host, tmpdir)
        finally:
            if tmpdir:
                host.rmtree(tmpdir)
            host.chdir(orig_wd)

        if ret is not None:
            self.assertEqual(actual_ret, ret)
        if out is not None:
            self.assertEqual(actual_out, out)
        if err is not None:
            self.assertEqual(actual_err, err)
        if exp_files:
            self.assert_files(exp_files, actual_files, files_to_ignore)

        return actual_ret, actual_out, actual_err, actual_files
