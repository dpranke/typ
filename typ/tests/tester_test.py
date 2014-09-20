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
    def test_version(self):
        self.check('--version', ret=0, out='0.2\n')

    def test_fail(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check([], files=files, ret=1)

    def test_retry_limit(self):
        files = {'fail_test.py': FAILING_TEST}
        ret, out, err, _ = self.check(['--retry-limit', '2'], files=files)
        self.assertEqual(ret, 1)
        self.assertIn('Retrying failed tests', out)
        lines = out.splitlines()
        self.assertEqual(len([l for l in lines if 'test_fail failed:' in l]),
                         3)

    def test_skip(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check(['-x', '*test_fail*'], files=files, ret=1,
                   out='No tests to run.\n')

    def test_serial(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['--serial', '*test_pass*'], files=files, ret=0)

    def test_dryrun(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-n'], files=files, ret=0)

    def test_find(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-l'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.py'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.PassingTest.test_pass'], files=files,
                   ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')


class TestTester(TestsMixin, test_case.MainTestCase):
    prog = [sys.executable, '-m', 'typ']

    def test_debugger(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-d'], stdin='quit()\n', files=files, ret=0)

    def test_coverage(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-c'], files=files, ret=0)

    def test_find(self):
        super(TestTester, self).test_find()
        files = {'pass_test.py': PASSING_TEST}


# class TestMain(TestsMixin, test_case.MainTestCase):
class TestMain(TestsMixin):
    def call(self, host, argv, stdin, env):
        host.stdin = StringIO.StringIO(stdin)
        host.stdout = StringIO.StringIO()
        host.stderr = StringIO.StringIO()
        orig_sys_path = sys.path[:]
        try:
            ret = tester.main(['--no-trapping'] + argv, host)
            return ret, host.stdout.getvalue(), host.stderr.getvalue()
        finally:
            sys.path = orig_sys_path
