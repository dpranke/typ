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
import fnmatch
import re
import sys
import unittest

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


class FakeTestLoader(object):
    def __init__(self, host, orig_sys_path):
        self.host = host
        self.orig_sys_path = orig_sys_path

    def discover(self, start_dir, pattern='test*.py', top_level_dir=None):
        h = self.host
        all_files = h.files_under(start_dir)
        matching_files = [f for f in all_files if
                          fnmatch.fnmatch(h.basename(f), pattern)]
        suite = unittest.TestSuite()
        for f in matching_files:
            suite.addTests(self._loadTestsFromFile(h.join(start_dir, f),
                                                   top_level_dir))
        return suite

    def _loadTestsFromFile(self, path, top_level_dir='.'):
        h = self.host
        rpath = h.relpath(path, top_level_dir)
        module_name = (h.splitext(rpath)[0]).replace(h.sep, '.')
        class_name = ''
        suite = unittest.TestSuite()
        for l in h.read_text_file(path).splitlines():
            m = re.match('class (.+)\(', l)
            if m:
                class_name = m.group(1)
            m = re.match('.+def (.+)\(', l)
            if m:
                method_name = m.group(1)
                tc = FakeTestCase('%s.%s.%s' % (module_name, class_name,
                                                method_name))
                suite.addTest(tc)
        return suite

    def loadTestsFromName(self, name, module=None):
        h = self.host
        comps = name.split('.')
        path = '/'.join(comps)
        if len(comps) == 1:
            if h.isdir(path):
                # package
                return self.discover(path)
            if h.isfile(path + '.py'):
                # module
                return self._loadTestsFromFile(path + '.py')
        if len(comps) == 2:
            if h.isfile(comps[0] + '.py'):
                # module + class
                suite = self._loadTestsFromFile(comps[0] + '.py')
                return unittest.TestSuite([t for t in suite._tests if
                                           t.id().startswith(name)])

            for d in [d for d in sys.path if d not in self.orig_sys_path]:
                path = h.join(d, comps[0], comps[1] + '.py')
                if h.isfile(path):
                    # package + module
                    suite = self._loadTestsFromFile(path, d)
                    return unittest.TestSuite([t for t in suite._tests if
                                                t.id().startswith(name)])
                if h.isdir(d, comps[0], comps[1]):
                    # package
                    return self.discover(path)

            # no match
            return unittest.TestSuite()

        module_name = '.'.join(comps[:-2])
        fname = module_name.replace('.', h.sep) + '.py'

        for d in [d for d in sys.path if d not in self.orig_sys_path]:
            path = h.join(d, fname)
            if h.isfile(path):
                # module + class + method
                suite = self._loadTestsFromFile(path, d)
                return unittest.TestSuite([t for t in suite._tests if
                                            t.id() == name])
            if h.isdir(d, comps[0], comps[1]):
                # package
                return self.discover(h.join(d, comps[0], comps[1]))

            fname = module_name.replace('.', h.sep) + '.' + comps[-2] + '.py'
            if h.isfile(h.join(d, fname)):
                # module + class
                suite = self._loadTestsFromFile(comps[0] + '.py', d)
                return unittest.TestSuite([t for t in suite._tests if
                                            t.id().startswith(name)])

        # no match
        return unittest.TestSuite()


class FakeTestCase(unittest.TestCase):
    def __init__(self, name):
        self._name = name
        comps = self._name.split('.')
        self._class_name = comps[:-1]
        method_name = comps[-1]
        setattr(self, method_name, self._run)
        super(FakeTestCase, self).__init__(method_name)

    def id(self):
        return self._name

    def __str__(self):
        return "%s (%s)" % (self._testMethodName, self._class_name)

    def __repr__(self):
        return "%s testMethod=%s" % (self._class_name, self._testMethodName)

    def _run(self):
        if 'fail' in self._testMethodName:
            self.fail()


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

    def test_missing_builder_name(self):
        self.check(['--test-results-server', 'localhost'], ret=2)

    def test_retry_limit(self):
        files = {'fail_test.py': FAILING_TEST}
        ret, out, err, _ = self.check(['--retry-limit', '2'], files=files)
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
