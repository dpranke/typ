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
import imp
import re
import sys
import unittest

from typ.host import Host


class _FakeLoader(object):

    def __init__(self, host):
        self.host = host

    def _path_for_name(self, fullname):
        return fullname.replace('.', '/') + '.py'

    def find_module(self, fullname, path=None):
        if self.host.isfile(self._path_for_name(fullname)):
            return self
        return None

    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]

        if not self.host.isfile(self._path_for_name(fullname)):
            return None
        code = self.get_code(fullname)
        is_pkg = self.is_package(fullname)
        mod = sys.modules.setdefault(fullname, imp.new_module(fullname))
        mod.__file__ = self._path_for_name(fullname)
        mod.__loader__ = self
        if is_pkg:
            mod.__path__ = []
            mod.__package__ = str(fullname)
        else:
            mod.__package__ = str(fullname.rpartition('.')[0])
        exec(code, mod.__dict__)
        return mod

    def get_code(self, fullname):
        return self.host.read_text_file(self._path_for_name(fullname))

    def is_package(self, fullname):
        return False


class FakeTestLoader(object):
    # invalid names pylint: disable=C0103
    # protected member _tests pylint: disable=W0212
    # unused args pylint: disable=W0613

    def __init__(self, host, orig_sys_path):
        self._host = host
        self.orig_sys_path = orig_sys_path
        self._unittest_loader = None
        self._module_loader = None
        self._module_loader_cls = _FakeLoader

    def __getstate__(self):
        return {
            'orig_sys_path': self.orig_sys_path,
            '_module_loader_cls': self._module_loader_cls,
            '_host': self._host,
            '_module_loader': None,
            '_unittest_loader': None,
        }

    def _revive(self):
        if not self._host:
            self._host = Host()
        if not self._module_loader:
            self._module_loader = self._module_loader_cls(self._host)
            sys.meta_path = [self._module_loader]
        if not self._unittest_loader:
            self._unittest_loader = unittest.TestLoader()

    def discover(self, start_dir, pattern='test*.py', top_level_dir=None):
        self._revive()
        h = self._host

        all_files = h.files_under(start_dir)
        matching_files = [f for f in all_files if
                          fnmatch.fnmatch(h.basename(f), pattern)]
        suite = unittest.TestSuite()
        for f in matching_files:
            suite.addTests(self._loadTestsFromFile(h.join(start_dir, f),
                                                   top_level_dir))
        return suite

    def _loadTestsFromFile(self, path, top_level_dir='.'):
        self._revive()
        h = self._host
        rpath = h.relpath(path, top_level_dir)
        module_name = (h.splitext(rpath)[0]).replace(h.sep, '.')

        module_loader = self._module_loader
        mod = module_loader.load_module(module_name)
        return self._unittest_loader.loadTestsFromModule(mod)

    def loadTestsFromName(self, name, module=None):  # pragma: no cover
        self._revive()
        h = self._host
        module_loader = self._module_loader

        comps = name.split('.')
        path = '/'.join(comps)
        test_path_dirs = [d for d in sys.path if d not in self.orig_sys_path]

        if len(comps) == 1:
            if h.isdir(path):
                # package
                return self.discover(path)
            if h.isfile(path + '.py'):
                # module
                return self._loadTestsFromFile(path + '.py')
            for d in test_path_dirs:
                path = h.join(d, comps[0] + '.py')
                if h.isfile(path):
                    # module
                    suite = self._loadTestsFromFile(path, d)
                    return _tests_matching_name(suite, name)
                if h.isdir(d, path):
                    # package
                    return self.discover(path)
            raise ImportError()

        if len(comps) == 2:
            if h.isfile(comps[0] + '.py'):
                # module + class
                suite = self._loadTestsFromFile(comps[0] + '.py')
                return _tests_matching_name(suite, name)

            for d in test_path_dirs:
                path = h.join(d, comps[0], comps[1] + '.py')
                if h.isfile(path):
                    # package + module
                    suite = self._loadTestsFromFile(path, d)
                    return _tests_matching_name(suite, name)
                if h.isdir(d, comps[0], comps[1]):
                    # package
                    return self.discover(path)

            # no match
            raise ImportError()

        module_name = '.'.join(comps[:-2])
        fname = module_name.replace('.', h.sep) + '.py'

        for d in test_path_dirs:
            path = h.join(d, fname)
            if h.isfile(path):
                # module + class + method
                suite = self._loadTestsFromFile(path, d)
                return _tests_matching_name(suite, name)
            if h.isdir(d, comps[0], comps[1]):
                # package
                return self.discover(h.join(d, comps[0], comps[1]))

            fname = module_name.replace('.', h.sep) + '.' + comps[-2] + '.py'
            if h.isfile(h.join(d, fname)):
                # module + class
                suite = self._loadTestsFromFile(comps[0] + '.py', d)
                return _tests_matching_name(suite, name)

        # no match
        return unittest.TestSuite()


def _tests_matching_name(suite, name, tests=None):
    def add_tests(obj, name):
        if isinstance(obj, unittest.TestSuite):
            for el in obj:
                add_tests(el, name)
        else:
            assert isinstance(obj, unittest.TestCase)
            if obj.id().startswith(name):
                tests.append(obj)

    if tests is None:
        tests = []
    add_tests(suite, name)
    if tests:
        return unittest.TestSuite(tests)
    raise AttributeError
