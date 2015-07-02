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

import fnmatch
import io
import shlex
import sys
import unittest


def convert_newlines(msg):
    """A routine that mimics Python's universal_newlines conversion."""
    return msg.replace('\r\n', '\n').replace('\r', '\n')


class TestCase(unittest.TestCase):
    child = None
    context = None
    maxDiff = 80 * 66


class MainTestCase(TestCase):
    prog = None
    func = None
    in_place = False
    files_to_ignore = []

    def _write_files(self, host, files):
        for path, contents in list(files.items()):
            dirname = host.dirname(path)
            if dirname:
                host.maybe_mkdir(dirname)
            host.write_text_file(path, contents)

    def _read_files(self, host, tmpdir):
        out_files = {}
        for f in host.files_under(tmpdir):
            if any(fnmatch.fnmatch(f, pat) for pat in self.files_to_ignore):
                continue
            key = f.replace(host.sep, '/')
            out_files[key] = host.read_text_file(tmpdir, f)
        return out_files

    def assert_files(self, expected_files, actual_files, files_to_ignore=None):
        files_to_ignore = files_to_ignore or []
        for k, v in expected_files.items():
            self.assertMultiLineEqual(expected_files[k], v)
        interesting_files = set(actual_files.keys()).difference(
            files_to_ignore)
        self.assertEqual(interesting_files, set(expected_files.keys()))

    def make_host(self):
        # If we are ever called by unittest directly, and not through typ,
        # this will probably fail.
        assert self.child
        return self.child.host

    def call(self, host, argv, prog, func, stdin, env):
        assert prog or func

        if prog and prog[0] == '<python>':
            cmd = [host.python_interpreter] + prog[1:] + argv
        else:
            cmd = prog + argv

        if func:
            return self._call_func(host, func, argv, stdin, env)
        return host.call(cmd, stdin=stdin, env=env)

    def _call_func(self, host, func, argv, stdin, env):
        stdin = unicode(stdin)
        host.stdin = io.StringIO(stdin)
        if env:
            host.getenv = env.get
        host.capture_output()
        orig_sys_path = sys.path[:]
        orig_sys_modules = list(sys.modules.keys())

        try:
            ret = func(host, argv)
        finally:
            out, err = host.restore_output()
            modules_to_unload = []
            for k in sys.modules:
                if k not in orig_sys_modules:
                    modules_to_unload.append(k)
            for k in modules_to_unload:
                del sys.modules[k]
            sys.path = orig_sys_path

        return ret, out, err


    def check(self, cmd=None, stdin=None, env=None, aenv=None, files=None,
              prog=None, func=None, cwd=None, host=None,
              ret=None, out=None, rout=None, err=None, rerr=None,
              exp_files=None,
              files_to_ignore=None, universal_newlines=True):
        # Too many arguments pylint: disable=R0913
        prog = prog or self.prog or []
        func = func or self.func
        host = host or self.make_host()
        argv = shlex.split(cmd) if isinstance(cmd, str) else cmd or []

        tmpdir = None
        orig_wd = host.getcwd()
        try:
            if self.in_place:
                assert exp_files is None
            else:
                tmpdir = host.mkdtemp()
                host.chdir(tmpdir)
                if files:
                    self._write_files(host, files)
                if cwd:
                    host.chdir(cwd)
            if aenv:
                env = host.env.copy()
                env.update(aenv)

            if self.child.debugger:  # pragma: no cover
                host.print_('')
                host.print_('cd %s' % tmpdir, stream=host.stdout.stream)
                host.print_(' '.join(prog + argv), stream=host.stdout.stream)
                host.print_('')
                import pdb
                dbg = pdb.Pdb(stdout=host.stdout.stream)
                dbg.set_trace()

            result = self.call(host, argv, prog, func, stdin, env)

            actual_ret, actual_out, actual_err = result
            if self.in_place:
                actual_files = None
            else:
                actual_files = self._read_files(host, tmpdir)
        finally:
            host.chdir(orig_wd)
            if tmpdir:
                host.rmtree(tmpdir)

        if universal_newlines:
            actual_out = convert_newlines(actual_out)
        if universal_newlines:
            actual_err = convert_newlines(actual_err)

        if ret is not None:
            self.assertEqual(ret, actual_ret)
        if out is not None:
            self.assertMultiLineEqual(out, actual_out)
        if rout is not None:
            self.assertRegexpMatches(actual_out, rout)
        if err is not None:
            self.assertMultiLineEqual(err, actual_err)
        if rerr is not None:
            self.assertRegexpMatches(actual_err, rerr)
        if exp_files:
            self.assert_files(exp_files, actual_files, files_to_ignore)

        return actual_ret, actual_out, actual_err, actual_files
