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
import os
import sys
import textwrap
import unittest


from typ import main
from typ import test_case
from typ import FakeHost
from typ import Host
from typ import VERSION
from typ.fakes.unittest_fakes import FakeTestLoader


d = textwrap.dedent


PASS_TEST_PY = """
import unittest
class PassingTest(unittest.TestCase):
    def test_pass(self):
        pass
"""


PASS_TEST_FILES = {'pass_test.py': PASS_TEST_PY}


FAIL_TEST_PY = """
import unittest
class FailingTest(unittest.TestCase):
    def test_fail(self):
        self.fail()
"""


FAIL_TEST_FILES = {'fail_test.py': FAIL_TEST_PY}


OUTPUT_TEST_PY = """
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


OUTPUT_TEST_FILES = {'output_test.py': OUTPUT_TEST_PY}


SF_TEST_PY = """
import sys
import unittest

class SkipMethods(unittest.TestCase):
    @unittest.skip('reason')
    def test_reason(self):
        self.fail()

    @unittest.skipIf(True, 'reason')
    def test_skip_if_true(self):
        self.fail()

    @unittest.skipIf(False, 'reason')
    def test_skip_if_false(self):
        self.fail()


class SkipSetup(unittest.TestCase):
    def setUp(self):
        self.skipTest('setup failed')

    def test_notrun(self):
        self.fail()


@unittest.skip('skip class')
class SkipClass(unittest.TestCase):
    def test_method(self):
        self.fail()

class SetupClass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.stdout.write('in setupClass\\n')
        sys.stdout.flush()
        assert False, 'setupClass failed'

    def test_method1(self):
        pass

    def test_method2(self):
        pass

class ExpectedFailures(unittest.TestCase):
    @unittest.expectedFailure
    def test_fail(self):
        self.fail()

    @unittest.expectedFailure
    def test_pass(self):
        pass
"""


SF_TEST_FILES = {'sf_test.py': SF_TEST_PY}


ST_TEST_PY = """
import unittest
from typ import test_case as typ_test_case

def setupProcess(child, context):
    if context is None:
        context = {'calls': 0}
    child.host.print_('setupProcess(%d): %s' % (child.worker_num, context))
    context['calls'] += 1
    return context


def teardownProcess(child, context):
    child.host.print_('\\nteardownProcess(%d): %s' %
                      (child.worker_num, context))


class UnitTest(unittest.TestCase):
    def test_one(self):
        self.assertFalse(hasattr(self, 'host'))
        self.assertFalse(hasattr(self, 'context'))

    def test_two(self):
        pass


class TypTest(typ_test_case.TestCase):
    def test_one(self):
        self.assertNotEquals(self.child, None)
        self.assertGreaterEqual(self.context['calls'], 1)
        self.context['calls'] += 1

    def test_two(self):
        self.assertNotEquals(self.context, None)
        self.assertGreaterEqual(self.context['calls'], 1)
        self.context['calls'] += 1
"""


ST_TEST_FILES = {'st_test.py': ST_TEST_PY}

LOAD_TEST_PY = """
import unittest
def load_tests(_, _2, _3):
    class BaseTest(unittest.TestCase):
        pass

    def method_fail(self):
        self.fail()

    def method_pass(self):
        pass

    setattr(BaseTest, "test_fail", method_fail)
    setattr(BaseTest, "test_pass", method_pass)
    suite = unittest.TestSuite()
    suite.addTest(BaseTest("test_fail"))
    suite.addTest(BaseTest("test_pass"))
    return suite
"""


LOAD_TEST_FILES = {'load_test.py': LOAD_TEST_PY}


path_to_main = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'entry_points.py')


class TestCli(test_case.MainTestCase):
    prog = [sys.executable, '-B', path_to_main]

    def test_bad_arg(self):
        self.check(['--bad-arg'], ret=2, out='',
                   rerr='.*: error: unrecognized arguments: --bad-arg\n')
        self.check(['-help'], ret=2, out='',
                   rerr=(".*: error: argument -h/--help: "
                         "ignored explicit argument 'elp'\n"))

    def test_bad_metadata(self):
        self.check(['--metadata', 'foo'], ret=2, err='',
                   out='Error: malformed --metadata "foo"\n')

    def test_basic(self):
        self.check([], files=PASS_TEST_FILES,
                   ret=0,
                   out=('[1/1] pass_test.PassingTest.test_pass passed\n'
                        '1 test run, 0 failures.\n'), err='')

    def test_coverage(self):
        try:
            import coverage  # pylint: disable=W0612
            self.check(['-c'], files=PASS_TEST_FILES, ret=0, err='',
                       out=d("""\
                             [1/1] pass_test.PassingTest.test_pass passed
                             1 test run, 0 failures.

                             Name        Stmts   Miss  Cover
                             -------------------------------
                             pass_test       4      0   100%
                             """))
        except ImportError:  # pragma: no cover
            self.check(['-c'], files=PASS_TEST_FILES, ret=1,
                       out='Error: coverage is not installed\n', err='')

    def test_debugger(self):
        if sys.version_info.major == 3:  # pragma: no cover
            self.check(['-d'], files=PASS_TEST_FILES, ret=2,
                       out='Error: --debugger does not work w/ Python3 yet.\n')
        else:
            _, out, _, _ = self.check(['-d'], stdin='quit()\n',
                                      files=PASS_TEST_FILES, ret=0, err='')
            self.assertIn('(Pdb) ', out)

    def test_dryrun(self):
        self.check(['-n'], files=PASS_TEST_FILES, ret=0, err='',
                   out=d("""\
                         [1/1] pass_test.PassingTest.test_pass passed
                         1 test run, 0 failures.
                         """))

    def test_error(self):
        files = {'err_test.py': d("""\
                                  import unittest
                                  class ErrTest(unittest.TestCase):
                                      def test_err(self):
                                          foo = bar
                                  """)}
        _, out, _, _ = self.check( [''], files=files, ret=1, err='')
        self.assertIn('[1/1] err_test.ErrTest.test_err failed unexpectedly',
                      out)
        self.assertIn('1 test run, 1 failure', out)

    def test_fail(self):
        _, out, _, _ = self.check([], files=FAIL_TEST_FILES, ret=1, err='')
        self.assertIn('fail_test.FailingTest.test_fail failed unexpectedly',
                      out)

    def test_file_list(self):
        files = PASS_TEST_FILES
        self.check(['-f', '-'], files=files, stdin='pass_test\n', ret=0)
        self.check(['-f', '-'], files=files, stdin='pass_test.PassingTest\n',
                   ret=0)
        self.check(['-f', '-'], files=files,
                   stdin='pass_test.PassingTest.test_pass\n',
                   ret=0)
        files = {'pass_test.py': PASS_TEST_PY,
                 'test_list.txt': 'pass_test.PassingTest.test_pass\n'}
        self.check(['-f', 'test_list.txt'], files=files, ret=0)

    def test_find(self):
        files = PASS_TEST_FILES
        self.check(['-l'], files=files, ret=0,
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test'], files=files, ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.py'], files=files, ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', './pass_test.py'], files=files, ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'pass_test.PassingTest.test_pass'], files=files,
                   ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')
        self.check(['-l', '.'], files=files, ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')

    def test_find_from_subdirs(self):
        files = {
            'foo/__init__.py': '',
            'foo/pass_test.py': PASS_TEST_PY,
            'bar/__init__.py': '',
            'bar/tmp': '',

        }
        self.check(['-l', '../foo/pass_test.py'], files=files, cwd='bar',
                   ret=0, err='',
                   out='foo.pass_test.PassingTest.test_pass\n')
        self.check(['-l', 'foo'], files=files, cwd='bar',
                   ret=0, err='',
                   out='foo.pass_test.PassingTest.test_pass\n')
        self.check(['-l', '--path', '../foo', 'pass_test'],
                   files=files, cwd='bar', ret=0, err='',
                   out='pass_test.PassingTest.test_pass\n')

    def test_help(self):
        self.check(['--help'], ret=0, rout='.*', err='')

    def test_import_failure(self):
        self.check(['-l', 'foo'], ret=1, out='',
                   rerr='Failed to load "foo": No module named \'?foo\'?\n')

        files = {'foo.py': 'import unittest'}
        self.check(['-l', 'foo.bar'], files=files, ret=1, out='',
                   err=('Failed to load "foo.bar": '
                        '\'module\' object has no attribute \'bar\'\n'))

    def test_interrupt(self):
        files = {'interrupt_test.py': d("""\
                                        import unittest
                                        class Foo(unittest.TestCase):
                                           def test_interrupt(self):
                                               raise KeyboardInterrupt()
                                        """)}
        self.check(['-j', '1'], files=files, ret=130, out='',
                   err='interrupted, exiting\n')

    def test_isolate(self):
        self.check(['--isolate', '*test_pass*'], files=PASS_TEST_FILES, ret=0,
                   out=('[1/1] pass_test.PassingTest.test_pass passed\n'
                        '1 test run, 0 failures.\n'), err='')

    def test_load_tests_single_worker(self):
        files = LOAD_TEST_FILES
        _, out, _, _ = self.check(['-j', '1', '-v'], files=files, ret=1,
                                  err='')
        self.assertIn('[1/2] load_test.BaseTest.test_fail failed', out)
        self.assertIn('[2/2] load_test.BaseTest.test_pass passed', out)
        self.assertIn('2 tests run, 1 failure.\n', out)

    def test_load_tests_multiple_workers(self):
        _, out, _, _ = self.check([], files=LOAD_TEST_FILES, ret=1, err='')

        # The output for this test is nondeterministic since we may run
        # two tests in parallel. So, we just test that some of the substrings
        # we care about are present.
        self.assertIn('test_pass passed', out)
        self.assertIn('test_fail failed', out)
        self.assertIn('2 tests run, 1 failure.\n', out)

    def test_missing_builder_name(self):
        self.check(['--test-results-server', 'localhost'], ret=2,
                   out=('Error: --builder-name must be specified '
                        'along with --test-result-server\n'
                        'Error: --master-name must be specified '
                        'along with --test-result-server\n'
                        'Error: --test-type must be specified '
                        'along with --test-result-server\n'), err='')

    def test_ninja_status_env(self):
        self.check(['-v', 'output_test.PassTest.test_out'],
                   files=OUTPUT_TEST_FILES, aenv={'NINJA_STATUS': 'ns: '},
                   out=d("""\
                         ns: output_test.PassTest.test_out passed
                         1 test run, 0 failures.
                         """), err='')

    def test_output_for_failures(self):
        _, out, _, _ = self.check(['output_test.FailTest'],
                                  files=OUTPUT_TEST_FILES,
                                  ret=1, err='')
        self.assertIn('[1/1] output_test.FailTest.test_out_err_fail '
                      'failed unexpectedly:\n'
                      '  hello on stdout\n'
                      '  hello on stderr\n', out)


    def test_retry_limit(self):
        _, out, _, _ = self.check(['--retry-limit', '2'],
                                  files=FAIL_TEST_FILES, ret=1, err='')
        self.assertIn('Retrying failed tests', out)
        lines = out.splitlines()
        self.assertEqual(len([l for l in lines
                              if 'test_fail failed unexpectedly:' in l]),
                         3)

    def test_setup_and_teardown_single_child(self):
        self.check(['--jobs', '1',
                    '--setup', 'st_test.setupProcess',
                    '--teardown', 'st_test.teardownProcess'],
                   files=ST_TEST_FILES, ret=0, err='',
                   out=d("""\
                         setupProcess(1): {'calls': 0}
                         [1/4] st_test.TypTest.test_one passed
                         [2/4] st_test.TypTest.test_two passed
                         [3/4] st_test.UnitTest.test_one passed
                         [4/4] st_test.UnitTest.test_two passed
                         teardownProcess(1): {'calls': 3}

                         4 tests run, 0 failures.
                         """))

    def test_skip(self):
        self.check(['--skip', '*test_fail*'], files=FAIL_TEST_FILES, ret=1,
                   out='No tests to run.\n', err='')

        files = {'fail_test.py': FAIL_TEST_PY,
                 'pass_test.py': PASS_TEST_PY}
        self.check(['-j', '1', '--skip', '*test_fail*'], files=files, ret=0,
                   out=('[1/2] fail_test.FailingTest.test_fail was skipped\n'
                        '[2/2] pass_test.PassingTest.test_pass passed\n'
                        '2 tests run, 0 failures.\n'), err='')

        # This tests that we print test_started updates for skipped tests
        # properly. It also tests how overwriting works.
        _, out, _, _ = self.check(['-j', '1', '--overwrite', '--skip',
                                   '*test_fail*'], files=files, ret=0,
                                  err='', universal_newlines=False)

        # We test this string separately and call out.strip() to
        # avoid the trailing \r\n we get on windows, while keeping
        # the \r's elsewhere in the string.
        self.assertMultiLineEqual(
            out.strip(),
            ('[0/2] fail_test.FailingTest.test_fail\r'
             '                                     \r'
             '[1/2] fail_test.FailingTest.test_fail was skipped\r'
             '                                                 \r'
             '[1/2] pass_test.PassingTest.test_pass\r'
             '                                     \r'
             '[2/2] pass_test.PassingTest.test_pass passed\r'
             '                                            \r'
             '2 tests run, 0 failures.'))

    def test_skips_and_failures(self):
        self.check(['-j', '1', '-v', '-v'], files=SF_TEST_FILES, ret=1, err='',
                   rout=('\[1/9\] sf_test.ExpectedFailures.test_fail failed:\n'
                         '  Traceback \(most recent call last\):\n'
                         '    File ".*sf_test.py", line 48, in test_fail\n'
                         '      self.fail\(\)\n'
                         '  AssertionError: None\n'
                         '\[2/9\] sf_test.ExpectedFailures.test_pass '
                         'passed unexpectedly\n'
                         '\[3/9\] sf_test.SetupClass.test_method1 '
                         'failed unexpectedly:\n'
                         '  in setupClass\n'
                         '  Traceback \(most recent call last\):\n'
                         '    File ".*sf_test.py", line 37, in setUpClass\n'
                         '      assert False, \'setupClass failed\'\n'
                         '  AssertionError: setupClass failed\n'
                         '\[4/9\] sf_test.SetupClass.test_method2 '
                         'failed unexpectedly:\n'
                         '  in setupClass\n'
                         '  Traceback \(most recent call last\):\n'
                         '    File ".*sf_test.py", line 37, in setUpClass\n'
                         '      assert False, \'setupClass failed\'\n'
                         '  AssertionError: setupClass failed\n'
                         '\[5/9\] sf_test.SkipClass.test_method '
                         'was skipped:\n'
                         '  skip class\n'
                         '\[6/9\] sf_test.SkipMethods.test_reason '
                         'was skipped:\n'
                         '  reason\n'
                         '\[7/9\] sf_test.SkipMethods.test_skip_if_false '
                         'failed unexpectedly:\n'
                         '  Traceback \(most recent call last\):\n'
                         '    File ".*sf_test.py", line 16, in '
                         'test_skip_if_false\n'
                         '      self.fail\(\)\n'
                         '  AssertionError: None\n'
                         '\[8/9\] sf_test.SkipMethods.test_skip_if_true '
                         'was skipped:\n'
                         '  reason\n'
                         '\[9/9\] sf_test.SkipSetup.test_notrun '
                         'was skipped:\n'
                         '  setup failed\n'
                         '9 tests run, 4 failures.\n'))

    def test_timing(self):
        # TODO: check output.
        self.check(['-t'], files=PASS_TEST_FILES, ret=0)

    def test_verbose(self):
        self.check(['-vv', '-j', '1', 'output_test.PassTest'],
                   files=OUTPUT_TEST_FILES, ret=0,
                   out=d("""\
                         [1/2] output_test.PassTest.test_err passed:
                           hello on stderr
                         [2/2] output_test.PassTest.test_out passed:
                           hello on stdout
                         2 tests run, 0 failures.
                         """), err='')

    def test_version(self):
        self.check('--version', ret=0, out=(VERSION + '\n'))


class TestMain(TestCli):
    prog = []

    def make_host(self):
        return Host()

    def call(self, host, argv, stdin, env):
        if sys.version_info.major == 2 and isinstance(stdin, str):
            stdin = unicode(stdin)
        host.stdin = io.StringIO(stdin)
        if env:
            host.getenv = env.get
        host.capture_output(divert=not self.child.debugger)
        orig_sys_path = sys.path[:]
        orig_sys_modules = sys.modules.keys()
        loader = unittest.TestLoader()

        try:
            ret = main(argv + ['-j', '1'], host, loader)
        finally:
            out, err = host.restore_output()
            sys.path = orig_sys_path
            modules_to_unload = [k for k in sys.modules if k not in
                                 orig_sys_modules]
            for k in modules_to_unload:
                del sys.modules[k]

        return ret, out, err

    def test_coverage(self):
        # TODO: This seems to be flaky.
        pass

    def test_debugger(self):
        # TODO: This fails when run with -j 1 for some reason.
        pass


class TestFakes(TestCli):
    prog = []

    def make_host(self):
        return FakeHost()

    def call(self, host, argv, stdin, env):
        if sys.version_info.major == 2 and isinstance(stdin, str):
            stdin = unicode(stdin)
        host.stdin = io.StringIO(stdin)
        if env:
            host.env = env
        host.capture_output(divert=not self.child.debugger)
        orig_sys_path = sys.path[:]
        orig_sys_modules = sys.modules.keys()
        loader = FakeTestLoader(host, orig_sys_path)

        try:
            ret = main(argv + ['-j', '1'], host, loader)
        finally:
            out, err = host.restore_output()
            sys.path = orig_sys_path
            modules_to_unload = [k for k in sys.modules if k not in
                                 orig_sys_modules]
            for k in modules_to_unload:
                del sys.modules[k]

        return ret, out, err

    def test_find(self):
        pass

    def test_find_from_subdirs(self):
        pass

    def test_debugger(self):
        # This fails because we cannot get the source code.
        pass

    def test_coverage(self):
        # This fails because we cannot get the source code.
        pass

    def test_import_failure(self):
        pass

    def test_output_for_failures(self):
        pass

    def test_setup_and_teardown_single_child(self):
        pass

    def test_skips_and_failures(self):
        pass

    def test_verbose(self):
        pass
