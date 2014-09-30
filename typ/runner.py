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
import importlib
import inspect
import json
import pdb
import unittest


from typ import json_results
from typ.arg_parser import ArgumentParser
from typ.host import Host
from typ.pool import make_pool
from typ.stats import Stats
from typ.printer import Printer
from typ.test_case import TestCase as TypTestCase
from typ.version import VERSION

try:
   from enum import Enum
except ImportError:
   Enum = object


class TestSet(object):
    def __init__(self, parallel_tests=None, isolated_tests=None,
                 tests_to_skip=None, context=None, setup_fn=None,
                 teardown_fn=None):
        self.parallel_tests = parallel_tests or []
        self.isolated_tests = isolated_tests or []
        self.tests_to_skip = tests_to_skip or []
        self.context = context
        self.setup_fn = setup_fn
        self.teardown_fn = teardown_fn


class ResultType(Enum): # no __init__ pylint: disable=W0232
    Pass = 0
    Fail = 1
    ImageOnlyFailure = 2
    Timeout = 3
    Crash = 4
    Skip = 5


class Result(object): # pragma: no cover
    # too many instance attributes  pylint: disable=R0902
    # too many arguments  pylint: disable=R0913
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
    def __init__(self, host=None, loader=None):
        self.host = host or Host()
        self.loader = loader or unittest.loader.TestLoader()
        self.printer = None
        self.stats = None
        self.cov = None
        self.top_level_dir = None
        self.args = None

        # initialize self.args to the defaults.
        parser = ArgumentParser(self.host)
        self.parse_args(parser, [])

    def main(self, argv=None):
        parser = ArgumentParser(self.host)
        self.parse_args(parser, argv)
        if parser.exit_status is not None:
            return parser.exit_status

        try:
            ret, _ = self.run()
            return ret
        except KeyboardInterrupt:
            self.print_("interrupted, exiting", stream=self.host.stderr)
            return 130

    def parse_args(self, parser, argv):
        self.args = parser.parse_args(args=argv)
        if parser.exit_status is not None:
            return


    def print_(self, msg='', end='\n', stream=None):
        self.host.print_(msg, end, stream=stream)

    def run(self, test_set=None, classifier=None, context=None,
            setup_fn=None, teardown_fn=None):
        ret = 0

        if self.args.version:
            self.print_(VERSION)
            return ret, None

        ret = self._set_up_runner()
        if ret:
            return ret, None

        if self.cov: # pragma: no cover
            self.cov.start()

        full_results = None

        if not test_set:
            ret, test_set = self.find_tests(self.args, classifier, context,
                                            setup_fn, teardown_fn)
        if not ret:
            ret, full_results = self._run_tests(test_set)

        if self.cov: # pragma: no cover
            self.cov.stop()

        if full_results:
            self._summarize(full_results)
            self.write_results(full_results)
            upload_ret = self.upload_results(full_results)
            if not ret:
                ret = upload_ret
            self.report_coverage()
        else:
            upload_ret = 0

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
            try:
                import coverage
            except ImportError:
                h.print_("Error: coverage is not installed")
                return 1
            self.cov = coverage.coverage()
        return 0

    def find_tests(self, args, classifier=None,
                   context=None, setup_fn=None, teardown_fn=None):
        if not context and self.args.context:
            context = json.loads(self.args.context)
        if not setup_fn and self.args.setup:
            setup_fn = _import_name(self.args.setup)
        if not teardown_fn and self.args.teardown:
            teardown_fn = _import_name(self.args.teardown)
        test_set = self._make_test_set(context=context,
                                       setup_fn=setup_fn,
                                       teardown_fn=teardown_fn)

        h = self.host

        def matches(name, globs):
            return any(fnmatch.fnmatch(name, glob) for glob in globs)

        def default_classifier(test_set, test):
            name = test.id()
            if matches(name, args.skip):
                test_set.tests_to_skip.append(name)
            elif matches(name, args.isolate):
                test_set.isolated_tests.append(name)
            else:
                test_set.parallel_tests.append(name)

        def add_names(obj):
            if isinstance(obj, unittest.suite.TestSuite):
                for el in obj:
                    add_names(el)
            else:
                classifier(test_set, obj)

        if args.tests:
            tests = args.tests
        elif args.file_list:
            if args.file_list == '-':
                s = h.stdin.read()
            else:
                s = h.read_text_file(args.file_list)
            tests = [line.strip() for line in s.splitlines()]
        else:
            tests = ['.']

        ret = 0
        loader = self.loader
        suffixes = args.suffixes
        top_level_dir = self.top_level_dir
        classifier = classifier or default_classifier
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

        # TODO: Add support for discovering setupProcess/teardownProcess?

        if not ret:
            test_set.parallel_tests = sorted(test_set.parallel_tests)
            test_set.isolated_tests = sorted(test_set.isolated_tests)
            test_set.tests_to_skip = sorted(test_set.tests_to_skip)
        else:
            test_set = None
        return ret, test_set

    def _run_tests(self, test_set):
        h = self.host
        if not test_set.parallel_tests and not test_set.isolated_tests:
            self.print_('No tests to run.')
            return 1, None

        if self.args.list_only:
            all_tests = sorted(test_set.parallel_tests +
                               test_set.isolated_tests)
            self.print_('\n'.join(all_tests))
            return 0, None

        all_tests = sorted(test_set.parallel_tests + test_set.isolated_tests +
                           test_set.tests_to_skip)
        result = self._run_one_set(self.stats, test_set)
        results = [result]

        failed_tests = list(json_results.failed_test_names(result))
        retry_limit = self.args.retry_limit

        while retry_limit and failed_tests:
            if retry_limit == self.args.retry_limit:
                self.flush()
                self.args.overwrite = False
                self.printer.should_overwrite = False
                self.args.verbose = min(self.args.verbose, 1)

            self.print_('')
            self.print_('Retrying failed tests (attempt #%d of %d)...' %
                        (self.args.retry_limit - retry_limit + 1,
                         self.args.retry_limit))
            self.print_('')

            stats = Stats(self.args.status_format, h.time, 1)
            stats.total = len(failed_tests)
            tests_to_retry = self._make_test_set(
                isolated_tests=failed_tests,
                context=test_set.context,
                setup_fn=test_set.setup_fn,
                teardown_fn=test_set.teardown_fn)
            result = self._run_one_set(stats, tests_to_retry)
            results.append(result)
            failed_tests = list(json_results.failed_test_names(result))
            retry_limit -= 1

        if retry_limit != self.args.retry_limit:
            self.print_('')

        full_results = json_results.make_full_results(self.args.metadata,
                                                      int(h.time()),
                                                      all_tests, results)
        return (json_results.exit_code_from_full_results(full_results),
                full_results)

    def _make_test_set(self, parallel_tests=None, isolated_tests=None,
                       tests_to_skip=None, context=None, setup_fn=None,
                       teardown_fn=None):
        parallel_tests = parallel_tests or []
        isolated_tests = isolated_tests or []
        tests_to_skip = tests_to_skip or []
        return TestSet(sorted(parallel_tests), sorted(isolated_tests),
                       sorted(tests_to_skip), context, setup_fn, teardown_fn)

    def _run_one_set(self, stats, test_set):
        stats.total = (len(test_set.parallel_tests) +
                       len(test_set.isolated_tests) +
                       len(test_set.tests_to_skip))
        result = TestResult()
        self._skip_tests(stats, result, test_set.tests_to_skip)
        self._run_list(stats, result, test_set, test_set.parallel_tests,
                       self.args.jobs)
        self._run_list(stats, result, test_set, test_set.isolated_tests, 1)
        return result

    def _skip_tests(self, stats, result, tests_to_skip):
        for test_name in tests_to_skip:
            stats.started += 1
            self._print_test_started(stats, test_name)
            result.addSkip(test_name, '')
            stats.finished += 1
            self._print_test_finished(stats, test_name, 0, '', '', 0)


    def _run_list(self, stats, result, test_set, test_names, jobs):
        h = self.host
        running_jobs = set()

        jobs = min(len(test_names), jobs)
        if not jobs:
            return

        child = _Child(self, self.loader, test_set)
        pool = make_pool(h, jobs, _run_one_test, child,
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
    def __init__(self, parent, loader, test_set):
        self.host = None
        self.worker_num = None
        self.debugger = parent.args.debugger
        self.dry_run = parent.args.dry_run
        self.loader = loader
        self.passthrough = parent.args.passthrough
        self.context = test_set.context
        self.setup_fn = test_set.setup_fn
        self.teardown_fn = test_set.teardown_fn
        self.context_after_setup = None


def _setup_process(host, worker_num, child):
    child.host = host
    child.worker_num = worker_num

    if child.setup_fn:
        child.context_after_setup = child.setup_fn(child, child.context)
    else:
        child.context_after_setup = child.context
    return child


def _teardown_process(child):
    if child.teardown_fn:
        child.teardown_fn(child, child.context_after_setup)
    # TODO: Return a more structured result, including something from
    # the teardown function?
    return child.worker_num


def _import_name(name):  # pragma: no cover
    module_name, function_name = name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def _run_one_test(child, test_name):
    h = child.host

    if child.dry_run:
        return test_name, 0, '', '', 0

    try:
        suite = child.loader.loadTestsFromName(test_name)
    except Exception as e: # pragma: no cover
        # TODO: Figure out how to handle failures here.
        return (test_name, 1, '', 'failed to load %s: %s' % (test_name, str(e)),
                0)

    tests = list(suite)
    assert len(tests) == 1
    test_case = tests[0]
    if isinstance(test_case, TypTestCase):
        test_case.child = child
        test_case.context = child.context_after_setup

    result = TestResult()
    out = ''
    err = ''
    h.capture_output(divert=not child.passthrough)
    start = h.time()
    try:
        if child.debugger: # pragma: no cover
            # Access to protected member pylint: disable=W0212
            # TODO: add start_capture() and make it debugger-aware.
            test_func = getattr(test_case, test_case._testMethodName)
            fname = inspect.getsourcefile(test_func)
            lineno = inspect.getsourcelines(test_func)[1] + 1
            dbg = pdb.Pdb()
            dbg.set_break(fname, lineno)
            dbg.runcall(suite.run, result)
        else:
            suite.run(result)
        took = h.time() - start
    finally:
        out, err = h.restore_output()

    # TODO: return proper Results and handle skips and expected failures.
    if result.failures:
        return (test_name, 1, out, err + result.failures[0][1], took)
    if result.errors: # pragma: no cover
        return (test_name, 1, out, err + result.errors[0][1], took)
    return (test_name, 0, out, err, took)


class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super(TestResult, self).__init__(stream=stream,
                                         descriptions=descriptions,
                                         verbosity=verbosity)
        self.successes = []
