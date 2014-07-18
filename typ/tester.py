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
        printer = Printer(print_, should_overwrite)

        test_names = find_tests(args)
        if test_names is None:
            return 1

        if args.list_only:
            print_('\n'.join(sorted(test_names)))
            return 0
        return run_tests(args, printer, stats, test_names)
    finally:
        sys.stdout = orig_stdout
        sys.stderr = orig_stderr



def parse_args(argv):
    ap = argparse.ArgumentParser(prog='typ')
    ap.usage = '%(prog)s [options] tests...'
    ap.add_argument('-c', dest='coverage', action='store_true',
                    help='produce coverage information')
    ap.add_argument('-d', dest='debugger', action='store_true',
                    help='run a single test under the debugger')
    ap.add_argument('-f', dest='file_list', action='store',
                    help=('take the list of tests from the file '
                          '(use "-" for stdin)'))
    ap.add_argument('-l', dest='list_only', action='store_true',
                    help='list all the test names found in the given tests')
    ap.add_argument('-j', metavar='N', type=int, dest='jobs',
                    default=multiprocessing.cpu_count(),
                    help=('run N jobs in parallel [default=%(default)s, '
                          'derived from CPUs available]'))
    ap.add_argument('-n', dest='dry_run', action='store_true',
                    help=('dry run (don\'t run commands but act like they '
                          'succeeded)'))
    ap.add_argument('-p', dest='pass_through', action='store_true',
                    help='pass output through while running tests')
    ap.add_argument('-q', action='store_true', dest='quiet', default=False,
                    help='be quiet (only print errors)')
    ap.add_argument('-s', dest='status_format',
                    default=os.getenv('NINJA_STATUS', '[%f/%t] '),
                    help=('format for status updates '
                          '(defaults to NINJA_STATUS env var if set, '
                          '"[%%f/%%t] " otherwise)'))
    ap.add_argument('-t', dest='timing', action='store_true',
                    help="print timing info")
    ap.add_argument('-v', action='count', dest='verbose', default=0,
                    help="verbose logging")
    ap.add_argument('-V', '--version', action='store_true',
                    help='print pytest version ("%s")' % version())
    ap.add_argument('tests', nargs='*', default=[],
                    help=argparse.SUPPRESS)

    return ap.parse_args(argv)


def run_under_coverage(argv):
    argv = argv or sys.argv
    if '-c' in argv:
        argv.remove('-c')
    if '-j' in argv:
        argv.remove('-j')

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
        tests = args.tests

    for test in tests:
        if test.endswith('.py'):
            name = test.replace('/', '.')[:-3]
        else:
            name = test

        try:
            module_suite = loader.loadTestsFromName(name)
        except AttributeError as e:
            print_('Error: failed to import "%s"' % name, stream=sys.stderr)
            return None

        for suite in module_suite:
            if isinstance(suite, unittest.suite.TestSuite):
                test_names.extend(test_case.id() for test_case in suite)
            else:
                test_names.append(suite.id())
    return test_names


def run_tests(args, printer, stats, test_names):
    num_failures = 0
    running_jobs = set()
    stats.total = len(test_names)

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
    return 1 if num_failures > 0 else 0


def run_test(args, test_name):
    if args.dry_run:
        return test_name, 0, '', '', 0
    loader = unittest.loader.TestLoader()
    result = TestResult(pass_through=args.pass_through)
    suite = loader.loadTestsFromName(test_name)
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
        printer.update(stats.format() + test_name + suffix,
                       elide=(not args.verbose))

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


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print >> sys.stderr, "Interrupted, exiting"
        sys.exit(130)
