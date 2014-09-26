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

from typ import main
from typ import test_case
from typ.version import VERSION
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


OUTPUT_TESTS = """
import sys
import unittest

class PassTest(unittest.TestCase):
  def test_out(self):
    sys.stdout.write("hello on stdout\\n")
    sys.stdout.flush()

  def test_err(self):
    sys.stderr.write("hello on stderr\\n")

class FailTest(unittest.TestCase):
 def test_out_err_fail(self):
    sys.stdout.write("hello on stdout\\n")
    sys.stdout.flush()
    sys.stderr.write("hello on stderr\\n")
    self.fail()
"""


class TestCli(test_case.MainTestCase):
    prog = [sys.executable, '-m', 'typ']

    def test_bad_arg(self):
        self.check(['--bad-arg'], ret=2)
        self.check(['-help'], ret=2)

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
        self.check(['-l', '--path', '../foo', 'pass_test'],
                   files=files, cwd='bar', ret=0,
                   out='pass_test.PassingTest.test_pass\n')

    def test_help(self):
        self.check(['--help'], ret=0)

    def test_import_failure(self):
        self.check(['-l', 'foo'], ret=1, out='')

        files = {'foo.py': 'import unittest'}
        self.check(['-l', 'foo.bar'], files=files, ret=1, out='')

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

    def test_isolate(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['--isolate', '*test_pass*'], files=files, ret=0)

    def test_skip(self):
        files = {'fail_test.py': FAILING_TEST}
        self.check(['--skip', '*test_fail*'], files=files, ret=1,
                   out='No tests to run.\n')

        files = {'fail_test.py': FAILING_TEST,
                 'pass_test.py': PASSING_TEST}
        self.check(['--skip', '*test_fail*'], files=files, ret=0)

    def test_timing(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-t'], files=files, ret=0)

    def test_version(self):
        self.check('--version', ret=0, out=(VERSION + '\n'))

    def test_error(self):
        files = {'err_test.py': ('import unittest\n'
                                 'class ErrTest(unittest.TestCase):\n'
                                 '  def test_err(self):\n'
                                 '    foo = bar\n')}
        self.check([''], files=files, ret=1,
                   out=('[1/1] err_test.ErrTest.test_err failed:\n'
                        '  Traceback (most recent call last):\n'
                        '    File "err_test.py", line 4, in test_err\n'
                        '      foo = bar\n'
                        '  NameError: global name \'bar\' is not defined\n'
                        '1 test run, 1 failure.\n'),
                   err='')


    def test_verbose(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(['-vv', '-j', '1', 'output_tests.PassTest'],
                   files=files, ret=0,
                   out=('[1/2] output_tests.PassTest.test_err passed:\n'
                        '  hello on stderr\n'
                        '[2/2] output_tests.PassTest.test_out passed:\n'
                        '  hello on stdout\n'
                        '2 tests run, 0 failures.\n'),
                   err='')

    def test_ninja_status_env(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(['-v', 'output_tests.PassTest.test_out'],
                   files=files, env={'NINJA_STATUS': 'ns: '},
                   out=('ns: output_tests.PassTest.test_out passed\n'
                        '1 test run, 0 failures.\n'))

    def test_output_for_failures(self):
        files = {'output_tests.py': OUTPUT_TESTS}
        self.check(
            ['output_tests.FailTest'],
            files=files,
            ret=1,
            out=('[1/1] output_tests.FailTest.test_out_err_fail failed:\n'
                 '  hello on stdout\n'
                 '  hello on stderr\n'
                 '  Traceback (most recent call last):\n'
                 '    File "output_tests.py", line 18, in test_out_err_fail\n'
                 '      self.fail()\n'
                 '  AssertionError: None\n'
                 '1 test run, 1 failure.\n'),
            err='')

    def test_debugger(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-d'], stdin='quit()\n', files=files, ret=0)

    def test_coverage(self):
        files = {'pass_test.py': PASSING_TEST}
        self.check(['-c'], files=files, ret=0,
                   out=('[1/1] pass_test.PassingTest.test_pass passed\n'
                        '1 test run, 0 failures.\n'
                        '\n'
                        'Name        Stmts   Miss  Cover\n'
                        '-------------------------------\n'
                        'pass_test       4      0   100%\n'))


class TestMain(TestCli):
    prog = []

    def call(self, host, argv, stdin, env):
        host.stdin = StringIO.StringIO(stdin)
        host.stdout = StringIO.StringIO()
        host.stderr = StringIO.StringIO()
        if env:
            host.getenv = env.get
        orig_sys_path = sys.path[:]
        loader = FakeTestLoader(host, orig_sys_path)
        try:
            ret = main.main(argv, host, loader)
            return ret, host.stdout.getvalue(), host.stderr.getvalue()
        finally:
            sys.path = orig_sys_path

    # TODO: figure out how to make these tests pass w/ trapping output.
    def test_debugger(self):
        pass

    def test_coverage(self):
        pass

    def test_error(self):
        pass

    def test_verbose(self):
        pass

    def test_output_for_failures(self):
        pass
