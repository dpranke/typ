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
import enum
import fnmatch
import inspect
import io
import json
import pdb
import unittest


from typ import json_results
from typ.arg_parser import ArgumentParser
from typ.pool import make_pool
from typ.stats import Stats
from typ.printer import Printer
from typ.version import VERSION


class TestSet(object): # pragma: no cover
    def __init__(self, parallel_tests=None, serial_tests=None, skip_tests=None):
        self.parallel_tests = parallel_tests or []
        self.serial_tests = serial_tests or []
        self.skip_tests = skip_tests or []


class ResultType(enum.Enum):
    Pass = 0
    Fail = 1
    ImageOnlyFailure = 2
    Timeout = 3
    Crash = 4
    Skip = 5


class Result(object): # pragma: no cover
    def __init__(self, name, actual=None, unexpected=False, flaky=False,
                 expected=None,
                 out=None, err=None, code=None, started=None, took=None,
                 worker=None):
        self.name = name
        self.expected = expected or [ResultType.Pass]
        self.actual = actual
        self.unexpected = unexpected
        self.flaky = flaky
        self.out = out
        self.err = err
        self.code = code
        self.started = started
        self.took = took
        self.worker = worker


class ResultSet(object): # pragma: no cover
    def __init__(self):
        self.results = []

    def add(self, result):
        self.results.append(result)


class Runner(object):
    def __init__(self, host, loader):
        self.host = host
        self.args = None
        self.loader = loader
        self.printer = None
        self.stats = None
        self.cov = None
        self.top_level_dir = None

        self.isolated_tests = []
        self.parallel_tests = []
        self.tests_to_skip = []

    def main(self, argv=None):
        parser = ArgumentParser(self.host)
        self.parse_args(parser, argv)
        if parser.exit_status is not None:
            return parser.exit_status

        try:
            ret, full_results = self.run()
            if full_results:
                self.write_results(full_results)
                upload_ret = self.upload_results(full_results)
            else:
                upload_ret = 0
            self.report_coverage()
            return ret or upload_ret
        except KeyboardInterrupt:
            self.print_("interrupted, exiting", stream=self.host.stderr)
            return 130

    def parse_args(self, parser, argv):
        self.args = parser.parse_args(args=argv)
        if parser.exit_status is not None:
            return


    def print_(self, msg='', end='\n', stream=None):
        self.host.print_(msg, end, stream=stream)

    def run(self):
        if self.args.version:
            self.print_(VERSION)
            return 0, None

        self._set_up_runner()

        if self.cov: # pragma: no cover
            self.cov.start()

        full_results = None
        ret = self.find_tests()
        if not ret:
            ret, full_results = self._run_tests()

        if self.cov: # pragma: no cover
            self.cov.stop()

        if full_results:
            self._summarize(full_results)
        return ret, full_results

    def _set_up_runner(self):
        h = self.host
        args = self.args

        self.stats = Stats(args.status_format, h.time, args.jobs)
        self.printer = Printer(self.print_, args.overwrite, args.terminal_width)

        self.top_level_dir = args.top_level_dir
        if not self.top_level_dir:
            top_dir = h.getcwd()
            while h.exists(top_dir, '__init__.py'):
                top_dir = h.dirname(top_dir)
            self.top_level_dir = top_dir

        h.add_to_path(self.top_level_dir)

        for path in args.path:
            h.add_to_path(path)

        if args.coverage: # pragma: no cover
            self.cov = coverage.coverage()

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
                if matches(test_name, self.args.skip):
                    tests_to_skip.append(test_name)
                elif matches(test_name, self.args.isolate):
                    isolated_tests.append(test_name)
                else:
                    parallel_tests.append(test_name)

        if self.args.tests:
            tests = self.args.tests
        elif self.args.file_list:
            if self.args.file_list == '-':
                s = h.stdin.read()
            else:
                s = h.read_text_file(self.args.file_list)
            tests = [line.strip() for line in s.splitlines()]
        else:
            tests = ['.']

        ret = 0
        loader = self.loader
        suffixes = self.args.suffixes
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
            return 1, None

        if self.args.list_only:
            all_tests = sorted(self.parallel_tests + self.isolated_tests)
            self.print_('\n'.join(all_tests))
            return 0, None

        all_tests = sorted(self.parallel_tests + self.isolated_tests +
                           self.tests_to_skip)
        result = self._run_one_set(self.stats,
                                   self.parallel_tests,
                                   self.isolated_tests,
                                   self.tests_to_skip)
        results = [result]

        failed_tests = list(json_results.failed_test_names(result))
        retry_limit = self.args.retry_limit

        if retry_limit and failed_tests:
            self.print_('')
            self.print_('Retrying failed tests ...')
            self.print_('')

        while retry_limit and failed_tests:
            stats = Stats(self.args.status_format, h.time, 1)
            stats.total = len(failed_tests)
            result = self._run_one_set(stats, [], failed_tests, [])
            results.append(result)
            failed_tests = list(json_results.failed_test_names(result))
            retry_limit -= 1

        full_results = json_results.make_full_results(self.args.metadata,
                                                      int(h.time()),
                                                      all_tests, results)
        return (json_results.exit_code_from_full_results(full_results),
                full_results)

    def _run_one_set(self, stats, parallel_tests, serial_tests, tests_to_skip):
        stats.total = (len(parallel_tests) + len(serial_tests) +
                       len(tests_to_skip))
        result = TestResult()
        self._skip_tests(stats, result, tests_to_skip)
        self._run_list(stats, result, parallel_tests, self.args.jobs)
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
        pool = make_pool(h, jobs, _run_one_test, _Child(self, self.loader),
                         _setup_process, _teardown_process)
        try:
            while test_names or running_jobs:
                while test_names and (len(running_jobs) < self.args.jobs):
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
        if not self.args.quiet and self.args.overwrite:
            self.update(stats.format() + test_name,
                        elide=(not self.args.verbose))

    def _print_test_finished(self, stats, test_name, res, out, err, took):
        stats.add_time()
        suffix = '%s%s' % (' failed' if res else ' passed',
                           (' %.4fs' % took) if self.args.timing else '')
        if res:
            if out or err:
                suffix += ':\n'
            self.update(stats.format() + test_name + suffix, elide=False)
            for l in out.splitlines(): # pragma: no cover
                self.print_('  %s' % l)
            for l in err.splitlines(): # pragma: no cover
                self.print_('  %s' % l)
        elif not self.args.quiet:
            if self.args.verbose > 1 and (out or err): # pragma: no cover
                suffix += ':\n'
            self.update(stats.format() + test_name + suffix,
                        elide=(not self.args.verbose))
            if self.args.verbose > 1: # pragma: no cover
                for l in out.splitlines():
                    self.print_('  %s' % l)
                for l in err.splitlines():
                    self.print_('  %s' % l)
            if self.args.verbose: # pragma: no cover
                self.flush()

    def update(self, msg, elide=True):  # pylint: disable=W0613
        self.printer.update(msg, elide=True)

    def flush(self): # pragma: no cover
        self.printer.flush()

    def _summarize(self, full_results):
        num_tests = self.stats.finished
        num_failures = json_results.num_failures(full_results)

        if not self.args.quiet and self.args.timing:
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

    def write_results(self, full_results): # pragma: no cover
        if self.args.write_full_results_to:
            self.host.write_text_file(
                self.args.write_full_results_to,
                json.dumps(full_results, indent=2) + '\n')

    def upload_results(self, full_results): # pragma: no cover
        h = self.host
        if not self.args.test_results_server:
            return 0

        url, data, content_type = json_results.make_upload_request(
            self.args.test_results_server, self.args.builder_name,
            self.args.master_name, self.args.test_type,
            full_results)
        try:
            response = h.fetch(url, data, {'Content-Type': content_type})
            if response.code == 200:
                return 0
            h.print_('Uploading the JSON results failed with %d: "%s"' %
                        (response.code, response.read()))
        except Exception as e:
            h.print_('Uploading the JSON results raised "%s"\n' % str(e))
        return 1

    def report_coverage(self):
        if self.cov: # pragma: no cover
            self.host.print_()
            self.cov.report(show_missing=False, omit=self.args.coverage_omit)

    def exit_code_from_full_results(self, full_results): # pragma: no cover
        return json_results.exit_code_from_full_results(full_results)


class _Child(object):
    def __init__(self, parent, loader):
        self.debugger = parent.args.debugger
        self.dry_run = parent.args.dry_run
        self.loader = loader
        self.worker_num = None
        self.host = None


def _setup_process(host, worker_num, context):
    child = context
    child.host = host
    child.worker_num = worker_num
    trap(child.host.sys_module)
    return child


def _run_one_test(context_from_setup, test_name):
    child = context_from_setup
    h = child.host

    if child.dry_run:
        return test_name, 0, '', '', 0

    try:
        suite = child.loader.loadTestsFromName(test_name)
    except Exception as e: # pragma: no cover
        # TODO: This should be a very rare failure, but we need to figure out
        # how to test it.
        return (test_name, 1, '', 'failed to load %s: %s' % (test_name, str(e)),
                0)

    result = TestResult()
    start = h.time()
    out = ''
    err = ''
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
        try:
            start_capture(h.sys_module)
            suite.run(result)
        finally:
            out, err = stop_capture(h.sys_module)

    took = h.time() - start
    if result.failures:
        return (test_name, 1, out, err + result.failures[0][1], took)
    if result.errors: # pragma: no cover
        return (test_name, 1, out, err + result.errors[0][1], took)
    return (test_name, 0, out, err, took)


def _teardown_process(context_from_setup):
    child = context_from_setup
    release(child.host.sys_module)
    return child.worker_num


class TrappableStream(io.StringIO):
    def __init__(self, stream):
        super(TrappableStream, self).__init__()
        self.stream = stream
        self.trap = False

    def write(self, msg, *args, **kwargs): # pragma: no cover
        if self.trap:
            super(TrappableStream, self).write(unicode(msg), *args, **kwargs)
        else:
            self.stream.write(unicode(msg), *args, **kwargs)

    def flush(self, *args, **kwargs): # pragma: no cover
        if self.trap:
            super(TrappableStream, self).flush(*args, **kwargs)
        else:
            self.stream.flush(*args, **kwargs)

    def start_capture(self):
        self.truncate(0)
        self.trap = True

    def stop_capture(self):
        self.trap = False
        msg = self.getvalue()
        self.truncate(0)
        return msg


def trap(sys_module):
    sys_module.stdout = TrappableStream(sys_module.stdout)
    sys_module.stderr = TrappableStream(sys_module.stderr)


def release(sys_module):
    sys_module.stdout = sys_module.stdout.stream
    sys_module.stderr = sys_module.stderr.stream


def start_capture(sys_module):
    sys_module.stdout.start_capture()
    sys_module.stderr.start_capture()


def stop_capture(sys_module):
    out = sys_module.stdout.stop_capture()
    err = sys_module.stderr.stop_capture()
    return out, err


class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super(TestResult, self).__init__(stream=stream,
                                         descriptions=descriptions,
                                         verbosity=verbosity)
        self.successes = []
