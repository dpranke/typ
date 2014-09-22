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

import argparse
import fnmatch
import inspect
import io
import pdb
import subprocess
import sys
import unittest


from typ import json_results
from typ.host import Host
from typ.pool import make_pool
from typ.stats import Stats
from typ.printer import Printer


def version(host=None):
    return '0.3'


DEFAULT_STATUS_FORMAT = '[%f/%t] '

orig_stdout = sys.stdout
orig_stderr = sys.stderr


def main(argv=None, host=None, loader=None):
    host = host or _host()
    loader = loader or _loader()

    argv = argv or sys.argv[1:]
    try:
        args = parse_args(argv)
        if args.version:
            host.print_(version())
            return 0
        if args.coverage:
            return _run_under_coverage(argv, args.coverage_omit)
        if args.debugger:
            args.jobs = 1
            args.pass_through = True

        context = _setup_process(host, 0, (args, loader))
        try:
            return run(args, host, loader)
        finally:
            _teardown_process(context)
    except KeyboardInterrupt:
        host.print_("interrupted, exiting", stream=orig_stderr)
        return 130


def _win_main(host=None):
    # This function is called from __main__.py when running
    # 'python -m typ' on windows: in order to use multiprocessing on windows,
    # we need to ensure that the 'main' module is importable,
    # and __main__.py isn't.
    # This code instead spawns a subprocess and invokes tester.py directly;
    # We don't want to always spawn a subprocess, because that is more
    # heavyweight than it needs to be on other platforms.
    import subprocess
    proc = subprocess.Popen([sys.executable, __file__] + sys.argv[1:])
    try:
        proc.wait()
    except KeyboardInterrupt:
        # We may need a second wait in order to make sure the subprocess exits
        # completely.
        proc.wait()
    return proc.returncode


def _run_under_coverage(argv, coverage_omit):
    # TODO: import coverage and run in-line.
    if '-c' in argv:
        argv.remove('-c')
    if '-j' in argv:
        idx = argv.index('-j')
        argv.pop(idx)
        argv.pop(idx)
    if '--coverage-omit' in argv:
        idx = argv.index('--coverage-omit')
        argv.pop(idx)
        argv.pop(idx)

    subprocess.call(['coverage', 'erase'])
    res = subprocess.call(['coverage', 'run', '-m', 'typ', '-j', '1'] + argv)
    sys.stdout.write('\n')
    sys.stdout.flush()

    report_args = ['--omit', coverage_omit] if coverage_omit else []
    subprocess.call(['coverage', 'report'] + report_args)
    return res


def run(args, host=None, loader=None):
    host = host or _host()
    loader = loader or _loader()

    started_time = host.time()

    stats = Stats(args.status_format, host.time, started_time, args.jobs)
    should_overwrite = orig_stdout.isatty() and not args.verbose
    printer = Printer(host.print_, should_overwrite, cols=args.terminal_width)

    if args.top_level_dir:
        path = host.abspath(args.top_level_dir)
        host.add_to_path(path)
    else:
        top_dir = host.getcwd()
        while host.exists(top_dir, '__init__.py'):
            top_dir = host.dirname(top_dir)
        if top_dir != host.getcwd():
            host.add_to_path(top_dir)

    for path in args.path:
        host.add_to_path(path)

    test_names, serial_test_names, skip_test_names = find_tests(args, host,
                                                                loader)
    if not test_names and not serial_test_names:
        host.print_('No tests to run.')
        return 1

    if args.list_only:
        host.print_('\n'.join(sorted(test_names + serial_test_names)))
        return 0

    return run_tests_with_retries(args, printer, stats, test_names,
                                  serial_test_names, skip_test_names,
                                  host=host, loader=loader)


def trap_stdio(should_passthrough):
    sys.stdout = PassThrough(sys.stdout if should_passthrough else None)
    sys.stderr = PassThrough(sys.stderr if should_passthrough else None)


def release_stdio():
    sys.stdout = orig_stdout
    sys.stderr = orig_stderr


def parse_args(argv, host=None):
    host = host or _host()
    ap = argparse.ArgumentParser(prog='typ')
    ap.usage = '%(prog)s [options] [tests...]'
    ap.add_argument('-c', '--coverage', action='store_true',
                    help='produce coverage information')
    ap.add_argument('-d', '--debugger', action='store_true',
                    help='run a single test under the debugger')
    ap.add_argument('-f', '--file-list', metavar='FILENAME', action='store',
                    help=('Take the list of tests from the file '
                          '(use "-" for stdin).'))
    ap.add_argument('-l', '--list-only', action='store_true',
                    help='List all the test names found in the given tests.')
    ap.add_argument('-j', '--jobs', metavar='N', type=int,
                    default=default_job_count(),
                    help=('Run N jobs in parallel '
                          '(defaults to %(default)d, from CPUs available).'))
    ap.add_argument('-n', '--dry-run', action='store_true',
                    help=('Do not actually run the tests, act like they '
                          'succeeded.'))
    ap.add_argument('-p', '--pass-through', action='store_true',
                    help='Pass output through while running tests.')
    ap.add_argument('-q', '--quiet', action='store_true', default=False,
                    help='Be as quiet as possible (only print errors).')
    ap.add_argument('-s', '--status-format',
                    default=host.getenv('NINJA_STATUS', DEFAULT_STATUS_FORMAT),
                    help=('Format for status updates '
                          '(defaults to NINJA_STATUS env var if set, '
                          '"[%%f/%%t] " otherwise).'))
    ap.add_argument('-t', '--timing', action='store_true',
                    help='Print timing info.')
    ap.add_argument('-v', '--verbose', action='count', default=0,
                    help=('Log verbosely '
                          '(specify multiple times for more output).'))
    ap.add_argument('-P', '--path', action='append', default=[],
                    help=('add dir to sys.path'))
    ap.add_argument('-V', '--version', action='store_true',
                    help='Print the typ version ("%s") and exit.' % version())
    ap.add_argument('--builder-name',
                    help='Builder name to include in the uploaded data '
                         '(as shown on the buildbot waterfall).')
    ap.add_argument('--master-name',
                    help='Buildbot master name to include in the '
                         'uploaded data.')
    ap.add_argument('--metadata', action='append', default=[],
                    help=('Optional key=value metadata that will be included '
                          'in the results '
                          '(can be used for revision numbers, etc.).'))
    ap.add_argument('--retry-limit', type=int, default=0,
                    help='Retry each failure up to N times to de-flake things '
                         '(defaults to %(default)d, no retries).')
    ap.add_argument('--terminal-width', type=int, default=terminal_width(host),
                    help=('Width of output (defaults to '
                          'current terminal width, %(default)d).'))
    ap.add_argument('--test-results-server', default='',
                    help=('If specified, upload the full results to '
                          'this server.'))
    ap.add_argument('--test-type',
                    help=('Name of test type to include in the uploaded data '
                          '(e.g., "telemetry_unittests").'))
    ap.add_argument('--top-level-dir', default='.',
                    help=('Top directory of project '
                          '(used when running subdirs).'))
    ap.add_argument('--write-full-results-to', metavar='FILENAME',
                    action='store',
                    help='If specified, write the full results to that path.')
    ap.add_argument('--serial', metavar='glob', default=[],
                    action='append',
                    help='test globs to run serially (in isolation)')
    ap.add_argument('-x', '--exclude', metavar='glob', default=[],
                    action='append',
                    help='test globs to exclude')
    ap.add_argument('--suffixes', metavar='glob', default=[],
                    action='append',
                    help=('filename globs to look for '
                          '(defaults to "*_unittest.py", "*_test.py")'))
    ap.add_argument('--coverage-omit', default='*/typ/*',
                    help='globs to omit in coverage report')
    ap.add_argument('--no-trapping', action='store_true')
    ap.add_argument('tests', nargs='*', default=[],
                    help=argparse.SUPPRESS)

    args = ap.parse_args(argv)

    if not args.suffixes:
        args.suffixes = ['*_unittest.py', '*_test.py']

    for val in args.metadata:
        if '=' not in val:
            ap.error('Error: malformed metadata "%s"' % val)

    if (args.test_results_server and
        (not args.builder_name or not args.master_name or not args.test_type)):
        ap.error('Error: --builder-name, --master-name, and --test-type '
                 'must be specified along with --test-result-server.')

    return args



def find_tests(args, host=None, loader=None):
    host = host or _host()
    loader = loader or _loader()
    test_names = []
    serial_test_names = []
    skip_names = []

    def add_names_from_suite(obj):
        if isinstance(obj, unittest.suite.TestSuite):
            for el in obj:
                add_names_from_suite(el)
        else:
            test_name = obj.id()
            if any(fnmatch.fnmatch(test_name, glob) for glob in args.exclude):
                skip_names.append(test_name)
            elif any(fnmatch.fnmatch(test_name, glob) for glob in args.serial):
                serial_test_names.append(test_name)
            else:
                test_names.append(test_name)

    if args.file_list:
        if args.file_list == '-':
            s = host.stdin.read()
        else:
            s = host.read_text_file(args.file_list)
        tests = [line.strip() for line in s.splitlines()]
    else:
        tests = args.tests or ['.']

    for test in tests:
        try:
            if host.isfile(test):
                name = host.relpath(test, args.top_level_dir)
                if name.endswith('.py'):
                    name = name[:-3]
                if name.startswith('.' + host.sep):
                    name = name[2:]
                name = name.replace(host.sep, '.')
                add_names_from_suite(loader.loadTestsFromName(name))
            elif host.isdir(test):
                for suffix in args.suffixes:
                    add_names_from_suite(loader.discover(test, suffix,
                                                         args.top_level_dir))
            else:
                possible_dir = host.relpath(test.replace('.', host.sep),
                                            args.top_level_dir)
                if host.isdir(possible_dir):
                    for suffix in args.suffixes:
                        suite = loader.discover(possible_dir, suffix,
                                                args.top_level_dir)
                        add_names_from_suite(suite)
                else:
                    name = possible_dir.replace(host.sep, '.')
                    add_names_from_suite(loader.loadTestsFromName(name))
        except AttributeError as e:
            host.print_('Error: failed to import "%s": %s' % (test, str(e)),
                        stream=host.stderr)

    return test_names, serial_test_names, skip_names


def run_tests_with_retries(args, printer, stats, test_names, serial_test_names,
                           skip_test_names, host=None, loader=None):
    host = host or _host()
    loader = loader or _loader()
    all_test_names = test_names

    result = run_one_set_of_tests(args, printer, stats, test_names,
                                  serial_test_names, skip_test_names,
                                  host=host, loader=loader)
    results = [result]

    failed_tests = list(json_results.failed_test_names(result))
    retry_limit = args.retry_limit

    # When retrying failures, only run one test at a time.
    args.jobs = 1

    if retry_limit and failed_tests:
        printer.flush()
        printer.print_('')
        printer.print_('Retrying failed tests ...')
        printer.print_('')

    while retry_limit and failed_tests:
        stats = Stats(args.status_format, host.time, host.time(), args.jobs)
        stats.total = len(failed_tests)
        result = run_one_set_of_tests(args, printer, stats, failed_tests,
                                      [], [], host=host, loader=loader)
        results.append(result)
        failed_tests = list(json_results.failed_test_names(result))
        retry_limit -= 1

    full_results = json_results.full_results(args, all_test_names, results)
    json_results.write_full_results_if_necessary(args, full_results, host=host)

    err_occurred, err_str = json_results.upload_full_results_if_necessary(
        args, full_results, host=host)
    if err_occurred:
        for line in err_str.splitlines():
            host.print_(line)
        return 1

    return json_results.exit_code_from_full_results(full_results)


def run_one_set_of_tests(args, printer, stats, test_names, serial_test_names,
                         skip_test_names, host=None, loader=None):
    host = host or _host()
    loader = loader or _loader()
    num_failures = 0
    stats.total = (len(test_names) + len(serial_test_names) +
                   len(skip_test_names))

    result = TestResult()

    skip_tests(args, printer, stats, result, skip_test_names)

    num_failures += run_test_list(args, printer, stats, result,
                                  test_names, args.jobs, host, loader)
    num_failures += run_test_list(args, printer, stats, result,
                                  serial_test_names, 1, host, loader)

    if not args.quiet:
        if args.timing:
            timing_clause = ' in %.1fs' % (host.time() - stats.started_time)
        else:
            timing_clause = ''
        printer.update('%d tests run%s, %d failure%s.' %
                       (stats.finished, timing_clause, num_failures,
                        '' if num_failures == 1 else 's'))
        host.print_()

    return result


def skip_tests(args, printer, stats, result, test_names):
    for test_name in test_names:
        stats.started += 1
        _print_test_started(printer, args, stats, test_name)
        result.addSkip(test_name, '')
        stats.finished += 1
        _print_test_finished(printer, args, stats, test_name, 0, '', '', 0)


def run_test_list(args, printer, stats, result, test_names, jobs,
                  host=None, loader=None):
    host = host or _host()
    loader = loader or _loader
    num_failures = 0
    running_jobs = set()

    jobs = min(len(test_names), jobs)
    pool = make_pool(host, jobs, _run_test, (args, loader),
                     _setup_process, _teardown_process)
    try:
        while test_names or running_jobs:
            while test_names and (len(running_jobs) < args.jobs):
                test_name = test_names.pop(0)
                stats.started += 1
                pool.send(test_name)
                running_jobs.add(test_name)
                _print_test_started(printer, args, stats, test_name)

            test_name, res, out, err, took = pool.get()
            running_jobs.remove(test_name)
            if res:
                num_failures += 1
                result.errors.append((test_name, err))
            else:
                result.successes.append((test_name, err))
            stats.finished += 1
            _print_test_finished(printer, args, stats, test_name,
                                res, out, err, took)
        pool.close()
    finally:
        pool.join()

    return num_failures


def _setup_process(host, worker_num, args_and_loader):
    args, loader = args_and_loader
    if not args.no_trapping:
        trap_stdio(args.pass_through)
    return (host, worker_num, args_and_loader)


def _teardown_process(context):
    host, worker_num, (args, loader) = context
    if not args.no_trapping:
        release_stdio()
    return worker_num


def _run_test(context, test_name):
    host, worker_num, (args, loader) = context
    if args.dry_run:
        return test_name, 0, '', '', 0
    result = TestResult(pass_through=args.pass_through)
    try:
        suite = loader.loadTestsFromName(test_name)
    except Exception as e:
        return (test_name, 1, '', 'failed to load %s: %s' % (test_name, str(e)),
                0)
    start = host.time()
    if args.debugger:
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
    took = host.time() - start
    if result.failures:
        return (test_name, 1, result.out, result.err + result.failures[0][1],
                took)
    if result.errors:
        return (test_name, 1, result.out, result.err + result.errors[0][1],
                took)
    return (test_name, 0, result.out, result.err, took)


def _print_test_started(printer, args, stats, test_name):
    if not args.quiet and printer.should_overwrite:
        printer.update(stats.format() + test_name, elide=(not args.verbose))


def _print_test_finished(printer, args, stats, test_name, res, out, err, took):
    stats.add_time()
    suffix = '%s%s' % (' failed' if res else ' passed',
                         (' %.4fs' % took) if args.timing else '')
    if res:
        if out or err:
            suffix += ':\n'
        printer.update(stats.format() + test_name + suffix, elide=False)
        for l in out.splitlines():
            printer.print_('  %s' % l)
        for l in err.splitlines():
            printer.print_('  %s' % l)
    elif not args.quiet:
        if args.verbose > 1 and (out or err):
            suffix += ':\n'
        printer.update(stats.format() + test_name + suffix,
                       elide=(not args.verbose))
        if args.verbose > 1:
            for l in out.splitlines():
                printer.print_('  %s' % l)
            for l in err.splitlines():
                printer.print_('  %s' % l)


def _host():
    h = Host()
    h.stdout = orig_stdout
    h.stderr = orig_stderr
    return h


def _loader():
    return unittest.loader.TestLoader()


class PassThrough(io.StringIO):
    def __init__(self, stream=None):
        self.stream = stream
        super(PassThrough, self).__init__()

    def write(self, msg, *args, **kwargs):
        if self.stream:
            self.stream.write(unicode(msg), *args, **kwargs)
        super(PassThrough, self).write(unicode(msg), *args, **kwargs)

    def flush(self, *args, **kwargs):
        if self.stream:
            self.stream.flush(*args, **kwargs)
        super(PassThrough, self).flush(*args, **kwargs)


class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, stream=None, descriptions=None, verbosity=None,
                 pass_through=False):
        self.pass_through = pass_through
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


def default_job_count(host=None):
    host = host or _host()
    return host.cpu_count()


def terminal_width(host=None):
    host = host or _host()
    return host.terminal_width()


if __name__ == '__main__':
    sys.exit(main())
