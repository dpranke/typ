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

import coverage
import fnmatch
import inspect
import io
import json
import pdb
import sys
import unittest


from typ import json_results
from typ.arg_parser import ArgumentParser
from typ.pool import make_pool
from typ.stats import Stats
from typ.printer import Printer
from typ.version import VERSION


orig_stdout = sys.stdout
orig_stderr = sys.stderr


class Runner(object):
    def __init__(self, host, loader):
        self.builder_name = None
        self.coverage = False
        self.coverage_omit = None
        self.debugger = False
        self.dry_run = False
        self.skip = []
        self.file_list = None
        self.host = host
        self.isolate = []
        self.isolated_tests = []
        self.jobs = host.cpu_count()
        self.list_only = False
        self.loader = loader
        self.master_name = None
        self.metadata = []
        self.no_trapping = False
        self.passthrough = False
        self.parallel_tests = []
        self.path = []
        self.printer = None
        self.quiet = False
        self.retry_limit = 0
        self.should_overwrite = False
        self.suffixes = ['*_test.py', '*_unittest.py']
        self.stats = None
        self.status_format = '[%f/%t]'
        self.terminal_width = host.terminal_width()
        self.test_results_server = None
        self.test_type = None
        self.tests = []
        self.tests_to_skip = []
        self.timing = False
        self.top_level_dir = None
        self.verbose = False
        self.version = False
        self.write_full_results_to = None
        self._cov = None

    def main(self, argv=None):
        parser = ArgumentParser()
        exit_status, exit_message = self.parse_args(parser, argv)
        if exit_status is not None:
            if exit_status:
                self.print_(exit_message, stream=self.host.stderr)
            return exit_status

        try:
            full_results = self.run()
            self.write_results(full_results)
            upload_ret = self.upload_results(full_results)
            self.report_coverage()
            return self.exit_code_from_full_results(full_results) or upload_ret
        except KeyboardInterrupt:
            self.print_("interrupted, exiting")
            return 130

    def parse_args(self, parser, args):
        # TODO: Figure out how to handle suffixes, coverage-omit.
        parser.set_defaults(jobs=self.jobs,
                            status_format=self.status_format,
                            terminal_width=self.terminal_width)

        # TODO: Decide if this is sufficiently idiot-proof.
        parser.parse_args(args=args, namespace=self)
        return parser.exit_status, parser.exit_message

    def print_(self, msg='', end='\n', stream=None):
        self.host.print_(msg, end, stream=stream)

    def run(self):
        if self.version:
            self.print_(VERSION + '\n')
            return 0

        ret = self._validate()
        if ret:
            return ret

        if not self.tests:
            ret = self.find_tests()
            if ret:
                return ret

        full_results = self._run_tests()
        self._summarize(full_results)
        return full_results

    def _validate(self):
        ret = 0
        h = self.host
        for val in self.metadata:
            if '=' not in val:
                self.print_('Error: malformed --metadata "%s"' % val)
                ret = 2

        if self.test_results_server:
            if not self.builder_name:
                self.print_('Error: --builder-name must be specified along '
                            'with --test-result-server')
                ret = 2
            if not self.master_name:
                self.print_('Error: --master-name must be specified along '
                            'with --test-result-server')
                ret = 2
            if not self.test_type:
                self.print_('Error: --test_type must be specified along '
                            'with --test-result-server')
                ret = 2

        if self.debugger:
            self.jobs = 1
            self.passthrough = True

        if self.coverage:
            self.jobs = 1

        self.stats = Stats(self.status_format, h.time, self.jobs)

        should_overwrite = h.stdout.isatty() and not self.verbose
        self.printer = Printer(self.print_, should_overwrite,
                               cols=self.terminal_width)

        if not self.top_level_dir:
            top_dir = h.getcwd()
            while h.exists(top_dir, '__init__.py'):
                top_dir = h.dirname(top_dir)
            h.top_level_dir = top_dir

        h.add_to_path(h.top_level_dir)

        for path in self.path:
            h.add_to_path(path)

        if self.coverage:
            self._cov = coverage.coverage()

        return ret

    def find_tests(self):
        isolated_tests = []
        parallel_tests = []
        tests_to_skip = []

        h = self.host

        def matches(name, globs):
            return any(fnmatch.fnmatch(name, glob) for glob in globs)

        def add_names(obj):
            if isinstance(obj, unittest.suite.TestSuite):
                for el in obj:
                    add_names(el)
            else:
                test_name = obj.id()
                if matches(test_name, self.skip):
                    tests_to_skip.append(test_name)
                elif matches(test_name, self.isolate):
                    isolated_tests.append(test_name)
                else:
                    parallel_tests.append(test_name)

        if self.tests:
            tests = self.tests
        elif self.file_list:
            if self.file_list == '-':
                s = h.stdin.read()
            else:
                s = h.read_text_file(self.file_list)
            tests = [line.strip() for line in s.splitlines()]
        else:
            tests = ['.']

        ret = 0
        loader = self.loader
        suffixes = self.suffixes
        top_level_dir = self.top_level_dir
        for test in tests:
            try:
                if h.isfile(test):
                    name = h.relpath(test, top_level_dir)
                    if name.endswith('.py'):
                        name = name[:-3]
                    name = name.replace(h.sep, '.')
                    add_names(loader.loadTestsFromName(name))
                elif h.isdir(test):
                    for suffix in suffixes:
                        add_names(loader.discover(test, suffix, top_level_dir))
                else:
                    possible_dir = test.replace('.', h.sep)
                    if h.isdir(top_level_dir, possible_dir):
                        for suffix in suffixes:
                            suite = loader.discover(h.join(top_level_dir,
                                                           possible_dir),
                                                    suffix,
                                                    top_level_dir)
                            add_names(suite)
                    else:
                        add_names(loader.loadTestsFromName(test))
            except AttributeError as e:
                self.print_('Failed to load "%s": %s' % (test, str(e)),
                            stream=h.stderr)
                ret = 1
            except ImportError as e:
                self.print_('Failed to load "%s": %s' % (test, str(e)),
                            stream=h.stderr)
                ret = 1

        if not ret:
            self.parallel_tests = sorted(parallel_tests)
            self.isolated_tests = sorted(isolated_tests)
            self.tests_to_skip = sorted(tests_to_skip)
        return ret

    def _run_tests(self):
        h = self.host
        if not self.parallel_tests and not self.isolated_tests:
            self.print_('No tests to run.')
            return 1

        if self.list_only:
            all_tests = sorted(self.parallel_tests + self.isolated_tests)
            self.print_('\n'.join(all_tests))
            return 0

        all_tests = sorted(self.parallel_tests + self.isolated_tests +
                           self.tests_to_skip)
        result = self._run_one_set(self.stats,
                                   self.parallel_tests,
                                   self.isolated_tests,
                                   self.tests_to_skip)
        results = [result]

        failed_tests = list(json_results.failed_test_names(result))
        retry_limit = self.retry_limit

        if retry_limit and failed_tests:
            self.print_('')
            self.print_('Retrying failed tests ...')
            self.print_('')

        while retry_limit and failed_tests:
            stats = Stats(self.status_format, h.time, jobs=1)
            stats.total = len(failed_tests)
            result = self._run_one_set(stats, [], failed_tests, [])
            results.append(result)
            failed_tests = list(json_results.failed_test_names(result))
            retry_limit -= 1

        return json_results.make_full_results(self.metadata, h.time(),
                                              all_tests, results)

    def _run_one_set(self, stats, parallel_tests, serial_tests, tests_to_skip):
        stats.total = (len(parallel_tests) + len(serial_tests) +
                       len(tests_to_skip))
        result = TestResult()
        self._skip_tests(stats, result, tests_to_skip)
        self._run_list(stats, result, parallel_tests, self.jobs)
        self._run_list(stats, result, serial_tests, 1)
        return result

    def _skip_tests(self, stats, result, tests_to_skip):
        for test_name in tests_to_skip:
            stats.started += 1
            self._print_test_started(stats, test_name)
            result.addSkip(test_name, '')
            stats.finished += 1
            self._print_test_finished(stats, test_name, 0, '', '', 0)


    def _run_list(self, stats, result, test_names, jobs):
        h = self.host
        running_jobs = set()

        jobs = min(len(test_names), jobs)
        pool = make_pool(h, jobs, _run_one_test, (self, self.loader),
                         _setup_process, _teardown_process)
        try:
            while test_names or running_jobs:
                while test_names and (len(running_jobs) < self.jobs):
                    test_name = test_names.pop(0)
                    stats.started += 1
                    pool.send(test_name)
                    running_jobs.add(test_name)
                    self._print_test_started(stats, test_name)

                    test_name, res, out, err, took = pool.get()
                    running_jobs.remove(test_name)
                    if res:
                        result.errors.append((test_name, err))
                    else:
                        result.successes.append((test_name, err))
                    stats.finished += 1
                    self._print_test_finished(stats, test_name,
                                               res, out, err, took)
            pool.close()
        finally:
            pool.join()

    def _print_test_started(self, stats, test_name):
        if not self.quiet and self.should_overwrite:
            self.update(stats.format() + test_name, elide=(not self.verbose))

    def _print_test_finished(self, stats, test_name, res, out, err, took):
        stats.add_time()
        suffix = '%s%s' % (' failed' if res else ' passed',
                           (' %.4fs' % took) if self.timing else '')
        if res:
            if out or err:
                suffix += ':\n'
            self.update(stats.format() + test_name + suffix, elide=False)
            for l in out.splitlines(): # pragma: no cover
                self.print_('  %s' % l)
            for l in err.splitlines(): # pragma: no cover
                self.print_('  %s' % l)
        elif not self.quiet:
            if self.verbose > 1 and (out or err): # pragma: no cover
                suffix += ':\n'
            self.update(stats.format() + test_name + suffix,
                        elide=(not self.verbose))
            if self.verbose > 1: # pragma: no cover
                for l in out.splitlines():
                    self.print_('  %s' % l)
                for l in err.splitlines():
                    self.print_('  %s' % l)
            if self.verbose:
                self.flush()

    def update(self, msg, elide=True):  # pylint: disable=W0613
        self.printer.update(msg, elide=True)

    def flush(self):
        self.printer.flush()

    def _summarize(self, full_results):
        num_tests = self.stats.finished
        num_failures = json_results.num_failures(full_results)
        if not self.quiet:
            if self.timing:
                timing_clause = ' in %.1fs' % (self.host.time() -
                                               self.stats.started_time)
            else:
                timing_clause = ''
        self.update('%d test%s run%s, %d failure%s.' %
                    (num_tests,
                     '' if num_tests == 1 else 's',
                     timing_clause,
                     num_failures,
                     '' if num_failures == 1 else 's'))
        self.print_()

    def write_results(self, full_results):
        if self.write_full_results_to:
            self.host.write_text_file(json.dumps(full_results, indent=2) + '\n')

    def upload_results(self, full_results):
        h = self.host
        if self.test_results_server:
            url, data, content_type = json_results.make_upload_request(
                self.test_results_server, self.builder_name, self.master_name,
                self.test_type, full_results)
            try:
                response = h.fetch(url, data, {'Content-Type': content_type})
                if response.code == 200:
                    return 0
                h.print_('Uploading the JSON results failed with %d: "%s"' %
                         (response.code, response.read()))
                return 1
            except Exception as e:
                h.print_('Uploading the JSON results raised "%s"\n' % str(e))

    def report_coverage(self):
        if self._cov:
            self._cov.report(show_missing=False, omit=self.coverage_omit)

    def exit_code_from_full_results(self, full_results):
        return json_results.exit_code_from_full_results(full_results)


class _Child(object):
    def __init__(self, parent, loader):
        self.dry_run = parent.dry_run
        self.loader = loader
        self.quiet = parent.quiet
        self.should_passthrough = parent.passthrough
        self.should_trap_stdio = parent.trap_stdio
        self.verbose = parent.verbose
        self.worker_num = None
        self.host = None


def _setup_process(host, worker_num, context):
    child = context
    child.host = host
    child.worker_num = worker_num
    if child.should_trap_stdio:
        trap_stdio(child.should_passthrough)
    return child


def _run_one_test(context_from_setup, test_name):
    child = context_from_setup
    h = child.host

    if child.dry_run:
        return test_name, 0, '', '', 0

    result = TestResult(passthrough=child.passthrough)
    try:
        suite = child.loader.loadTestsFromName(test_name)
    except Exception as e: # pragma: no cover
        # TODO: This should be a very rare failure, but we need to figure out
        # how to test it.
        return (test_name, 1, '', 'failed to load %s: %s' % (test_name, str(e)),
                0)

    start = h.time()
    if child.debugger: # pragma: no cover
        # Access to a protected member  pylint: disable=W0212
        test_case = suite._tests[0]
        test_func = getattr(test_case, test_case._testMethodName)
        fname = inspect.getsourcefile(test_func)
        lineno = inspect.getsourcelines(test_func)[1] + 1
        dbg = pdb.Pdb()
        dbg.set_break(fname, lineno)
        dbg.runcall(suite.run, result)
    else:
        suite.run(result)

    took = h.time() - start
    if result.failures:
        return (test_name, 1, result.out, result.err + result.failures[0][1],
                took)
    if result.errors: # pragma: no cover
        return (test_name, 1, result.out, result.err + result.errors[0][1],
                took)
    return (test_name, 0, result.out, result.err, took)


def _teardown_process(context_from_setup):
    child = context_from_setup
    if child.should_trap_stdio:
        release_stdio()
    return child.worker_num


class PassThrough(io.StringIO):
    def __init__(self, stream=None):
        self.stream = stream
        super(PassThrough, self).__init__()

    def write(self, msg, *args, **kwargs):
        if self.stream: # pragma: no cover
            self.stream.write(unicode(msg), *args, **kwargs)
        super(PassThrough, self).write(unicode(msg), *args, **kwargs)

    def flush(self, *args, **kwargs):
        if self.stream: # pragma: no cover
            self.stream.flush(*args, **kwargs)
        super(PassThrough, self).flush(*args, **kwargs)


def trap_stdio(should_passthrough):
    sys.stdout = PassThrough(sys.stdout if should_passthrough else None)
    sys.stderr = PassThrough(sys.stderr if should_passthrough else None)


def release_stdio():
    sys.stdout = orig_stdout
    sys.stderr = orig_stderr



class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, stream=None, descriptions=None, verbosity=None,
                 passthrough=False):
        self.passthrough = passthrough
        self.out_pos = 0
        self.err_pos = 0
        self.out = ''
        self.err = ''
        self.successes = []
        super(TestResult, self).__init__(stream=stream,
                                         descriptions=descriptions,
                                         verbosity=verbosity)

    # "Invalid name" pylint: disable=C0103

    def startTest(self, test):
        self.out_pos = len(sys.stdout.getvalue())
        self.err_pos = len(sys.stderr.getvalue())

    def stopTest(self, test):
        self.out = sys.stdout.getvalue()[self.out_pos:]
        self.err = sys.stderr.getvalue()[self.err_pos:]
