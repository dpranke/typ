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

import fnmatch
import re
import sys
import unittest


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
