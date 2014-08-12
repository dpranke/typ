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
import inspect
import io
import multiprocessing
import os
import pdb
import subprocess
import sys
import time
import unittest


from typ import json_results
from typ.pool import make_pool
from typ.stats import Stats
from typ.printer import Printer


def version():
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, 'VERSION')) as fp:
        return fp.read().strip()


orig_stdout = sys.stdout
orig_stderr = sys.stderr


def main(argv=None):
    started_time = time.time()

    args = parse_args(argv)
    if args.version:
        print_(version())
        return 0
    if args.coverage:
        return run_under_coverage(argv)
    if args.debugger:
        args.jobs = 1
        args.pass_through = True

    sys.stdout = PassThrough(sys.stdout if args.pass_through else None)
    sys.stderr = PassThrough(sys.stderr if args.pass_through else None)

    try:
        stats = Stats(args.status_format, time.time, started_time, args.jobs)
        should_overwrite = orig_stdout.isatty() and not args.verbose
        printer = Printer(print_, should_overwrite, cols=args.terminal_width)

        if args.top_level_dir:
            path = os.path.abspath(args.top_level_dir)
            if path not in sys.path:
                sys.path.append(path)
        else:
            top_dir = os.getcwd()
            while os.path.exists(os.path.join(top_dir, '__init__.py')):
                top_dir = os.path.dirname(top_dir)
            if top_dir != os.getcwd() and top_dir not in sys.path:
                sys.path.append(top_dir)

        for path in args.path:
            ap = os.path.abspath(path)
            if ap not in sys.path:
                sys.path.append(ap)

        test_names = find_tests(args)
        if test_names is None:
            return 1

        if args.list_only:
            print_('\n'.join(sorted(test_names)))
            return 0

        return run_tests_with_retries(args, printer, stats, test_names)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr



def parse_args(argv):
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
                    default=multiprocessing.cpu_count(),
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
                    default=os.getenv('NINJA_STATUS', '[%f/%t] '),
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
    ap.add_argument('--all', action='store_true',
                    help='Include tests that are skipped by default.')
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
    ap.add_argument('--terminal-width', type=int, default=terminal_width(),
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
    ap.add_argument('tests', nargs='*', default=[],
                    help=argparse.SUPPRESS)

    args = ap.parse_args(argv)

    for val in args.metadata:
        if '=' not in val:
            ap.error('Error: malformed metadata "%s"' % val)

    if (args.test_results_server and
        (not args.builder_name or not args.master_name or not args.test_type)):
        ap.error('Error: --builder-name, --master-name, and --test-type '
                 'must be specified along with --test-result-server.')

    return args


def run_under_coverage(argv):
    argv = argv or sys.argv
    if '-c' in argv:
        argv.remove('-c')
    if '-j' in argv:
        idx = argv.index('-j')
        argv.pop(idx)
        argv.pop(idx)

    subprocess.call(['coverage', 'erase'])
    res = subprocess.call(['coverage', 'run', '-m', 'typ'] +
                          ['-j', '1'] + argv[1:])
    subprocess.call(['coverage', 'report', '--omit=*/typ/*'])
    return res


def find_tests(args):
    loader = unittest.loader.TestLoader()
    test_names = []
    if args.file_list:
        if args.file_list == '-':
            f = sys.stdin
        else:
            f = open(args.file_list)
        tests = [line.strip() for line in f.readlines()]
        f.close()
    else:
        tests = args.tests or ['.']

    for test in tests:
        try:
            if os.path.isfile(test):
                name = os.path.relpath(test, args.top_level_dir)
                if name.endswith('.py'):
                    name = name[:-3]
                if name.startswith('./'):
                    name = name[2:]
                name = name.replace('/', '.')
                module_suite = loader.loadTestsFromName(name)
            elif os.path.isdir(test):
                module_suite = loader.discover(test, '*_unittest.py',
                                               args.top_level_dir)
            else:
                possible_dir = os.path.relpath(test.replace('.', '/'),
                                               args.top_level_dir)
                if os.path.isdir(possible_dir):
                    module_suite = loader.discover(possible_dir,
                                                   '*_unittest.py',
                                                   args.top_level_dir)
                else:
                    name = possible_dir.replace('/', '.')
                    module_suite = loader.loadTestsFromName(name)
        except AttributeError as e:
            print_('Error: failed to import "%s": %s' % (name, str(e)),
                   stream=sys.stderr)
            return None

        add_names_from_suite(test_names, module_suite)
    return test_names


def add_names_from_suite(test_names, obj):
    if isinstance(obj, unittest.suite.TestSuite):
        for el in obj:
            add_names_from_suite(test_names, el)
    else:
        test_names.append(obj.id())


def run_tests_with_retries(args, printer, stats, test_names):
    all_test_names = test_names

    result = run_one_set_of_tests(args, printer, stats, test_names)
    results = [result]

    failed_tests = json_results.failed_test_names(result)
    retry_limit = args.retry_limit

    # When retrying failures, only run one test at a time.
    args.jobs = 1

    while retry_limit and failed_tests:
        result = run_one_set_of_tests(args, printer, stats, failed_tests)
        results.append(result)
        failed_tests = json_results.failed_test_names(result)
        retry_limit -= 1

    full_results = json_results.full_results(args, all_test_names, results)
    json_results.write_full_results_if_necessary(args, full_results)

    err_occurred, err_str = json_results.upload_full_results_if_necessary(
        args, full_results)
    if err_occurred:
        for line in err_str.splitlines():
            print_(line)
        return 1

    return json_results.exit_code_from_full_results(full_results)


def run_one_set_of_tests(args, printer, stats, test_names):
    num_failures = 0
    running_jobs = set()
    stats.total = len(test_names)

    result = TestResult()
    pool = make_pool(args.jobs, run_test, args)
    try:
        while test_names or running_jobs:
            while test_names and (len(running_jobs) < args.jobs):
                test_name = test_names.pop(0)
                stats.started += 1
                pool.send(test_name)
                running_jobs.add(test_name)
                print_test_started(printer, args, stats, test_name)

            test_name, res, out, err, took = pool.get()
            running_jobs.remove(test_name)
            if res:
                num_failures += 1
                result.errors.append((test_name, err))
            else:
                result.successes.append((test_name, err))
            stats.finished += 1
            print_test_finished(printer, args, stats, test_name,
                                res, out, err, took)
        pool.close()
    finally:
        pool.join()

    if not args.quiet:
        if args.timing:
            timing_clause = ' in %.4fs' % (time.time() - stats.started_time)
        else:
            timing_clause = ''
        printer.update('%d tests run%s, %d failure%s.' %
                       (stats.finished, timing_clause, num_failures,
                        '' if num_failures == 1 else 's'))
        print_()
    return result


def run_test(args, test_name):
    if args.dry_run:
        return test_name, 0, '', '', 0
    loader = unittest.loader.TestLoader()
    result = TestResult(pass_through=args.pass_through)
    try:
        suite = loader.loadTestsFromName(test_name)
    except Exception as e:
        import pdb; pdb.set_trace()
        return (test_name, 1, '', 'failed to load %s: %s' % (test_name, str(e)),
                0)
    start = time.time()
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
    took = time.time() - start
    if result.failures:
        return (test_name, 1, result.out, result.err + result.failures[0][1],
                took)
    if result.errors:
        return (test_name, 1, result.out, result.err + result.errors[0][1],
                took)
    return (test_name, 0, result.out, result.err, took)


def print_test_started(printer, args, stats, test_name):
    if not args.quiet and printer.should_overwrite:
        printer.update(stats.format() + test_name, elide=(not args.verbose))


def print_test_finished(printer, args, stats, test_name, res, out, err, took):
    stats.add_time()
    suffix = '%s%s' % (' failed' if res else ' passed',
                         (' %.4fs' % took) if args.timing else '')
    if res:
        if out or err:
            suffix += ':\n'
        printer.update(stats.format() + test_name + suffix, elide=False)
        for l in out.splitlines():
            print_('  %s' % l)
        for l in err.splitlines():
            print_('  %s' % l)
    elif not args.quiet:
        if args.verbose > 1 and (out or err):
            suffix += ':\n'
        printer.update(stats.format() + test_name + suffix,
                       elide=(not args.verbose))
        if args.verbose > 1:
            for l in out.splitlines():
                print_('  %s' % l)
            for l in err.splitlines():
                print_('  %s' % l)


def print_(msg='', end='\n', stream=orig_stdout):
    stream.write(str(msg) + end)
    stream.flush()


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


def terminal_width():
    """Returns sys.maxint if the width cannot be determined."""
    try:
        if sys.platform == 'win32':
            # From http://code.activestate.com/recipes/ \
            #   440694-determine-size-of-console-window-on-windows/
            from ctypes import windll, create_string_buffer

            STDERR_HANDLE = -12
            handle = windll.kernel32.GetStdHandle(STDERR_HANDLE)

            SCREEN_BUFFER_INFO_SZ = 22
            buf = create_string_buffer(SCREEN_BUFFER_INFO_SZ)

            if windll.kernel32.GetConsoleScreenBufferInfo(handle, buf):
                import struct
                fields = struct.unpack("hhhhHhhhhhh", buf.raw)
                left = fields[5]
                right = fields[7]

                # Note that we return 1 less than the width since writing
                # into the rightmost column automatically performs a line feed.
                return right - left
            return sys.maxint
        else:
            import fcntl
            import struct
            import termios
            packed = fcntl.ioctl(sys.stderr.fileno(),
                                 termios.TIOCGWINSZ, '\0' * 8)
            _, columns, _, _ = struct.unpack('HHHH', packed)
            return columns
    except Exception:
        return sys.maxint


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print >> sys.stderr, "Interrupted, exiting"
        sys.exit(130)
