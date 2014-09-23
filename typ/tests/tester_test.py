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

import StringIO
import sys

from typ import tester
from typ import test_case
from typ.fakes.unittest_fakes import FakeTestLoader


PASSING_TEST = """
import unittest
class PassingTest(unittest.TestCase):
    def test_pass(self):
        pass
"""


FAILING_TEST = """
import unittest
class FailingTest(unittest.TestCase):
    def test_fail(self):
        self.fail()
"""


class TestsMixin(object):
    def test_bad_metadata(self):
        self.check(['--metadata', 'foo'], ret=2)

    def test_dryrun(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-n'], files=files, ret=0)

    def test_fail(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check([], files=files, ret=1)

    def test_file_list(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-f', '-'], files=files, stdin='pass_test\n', ret=0)
        self.check(['-f', '-'], files=files, stdin='pass_test.PassingTest\n',
                   ret=0)
        self.check(['-f', '-'], files=files,
                   stdin='pass_test.PassingTest.test_pass\n',
                   ret=0)
        files = {'pass_test.py': PASSING_TEST,
                 'test_list.txt': 'pass_test.PassingTest.test_pass\n'}
        self.check(['-f', 'test_list.txt'], files=files, ret=0)

    def test_find(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-l'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.py'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', './pass_test.py'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.PassingTest.test_pass'], files=files,
                   ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')

    def test_find_from_subdirs(self):
        files = {
            'foo/__init__.py': '',
            'foo/pass_test.py': PASSING_TEST,
            'bar/__init__.py': '',
            'bar/tmp': '',

        }
        self.check(['-l', '../foo/pass_test.py'], files=files, cwd='bar',
                   ret=0, out='foo.pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'foo'], files=files, cwd='bar',
                   ret=0, out='foo.pass_test.PassingTest.test_pass\n')

    def test_help(self):
        self.check(['--help'], ret=0)

    def test_interrupt(self):
        files = {'interrupt_test.py': ('import unittest\n'
                                       'class Foo(unittest.TestCase):\n'
                                       '    def test_interrupt(self):\n'
                                       '        raise KeyboardInterrupt()\n')}
        self.check(['-j', '1'], files=files, ret=130,
                   err='interrupted, exiting\n')

    def test_missing_builder_name(self):
        self.check(['--test-results-server', 'localhost'], ret=2)

    def test_retry_limit(self):
        files = {'fail_test.py': FAILING_TEST}
        ret, out, _, _ = self.check(['--retry-limit', '2'], files=files)
        self.assertEqual(ret, 1)
        self.assertIn('Retrying failed tests', out)
        lines = out.splitlines()
        self.assertEqual(len([l for l in lines if 'test_fail failed:' in l]),
                         3)

    def test_serial(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['--serial', '*test_pass*'], files=files, ret=0)

    def test_skip(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check(['-x', '*test_fail*'], files=files, ret=1,
                   out='No tests to run.\n')

    def test_version(self):
        self.check('--version', ret=0, out=(tester.version() + '\n'))


class TestCli(TestsMixin, test_case.MainTestCase):
    prog = [sys.executable, '-m', 'typ']

    def test_debugger(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-d'], stdin='quit()\n', files=files, ret=0)

    def test_coverage(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-c'], files=files, ret=0)


class TestMain(TestsMixin, test_case.MainTestCase):
    def call(self, host, argv, stdin, env):
        host.stdin = StringIO.StringIO(stdin)
        host.stdout = StringIO.StringIO()
        host.stderr = StringIO.StringIO()
        orig_sys_path = sys.path[:]
        loader = FakeTestLoader(host, orig_sys_path)
        try:
            ret = tester.main(['--no-trapping'] + argv, host, loader)
            return ret, host.stdout.getvalue(), host.stderr.getvalue()
        finally:
            sys.path = orig_sys_path
