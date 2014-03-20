import argparse
import multiprocessing
import os
import subprocess
import sys
import time
import unittest
import StringIO


from pytest_pool import make_pool
from pytest_stats import Stats
from pytest_printer import Printer


def main(argv=None):
    started_time = time.time()

    args = parse_args(argv)
    if args.timing and args.verbose == 0:
        args.verbose = 1
    if args.coverage:
        return run_under_coverage(argv)

    stats = Stats(args.status_format, time.time, started_time)
    should_overwrite = sys.stdout.isatty() and not args.verbose
    printer = Printer(print_, should_overwrite)

    test_names = find_tests(args)
    return run_tests(args, printer, stats, test_names)


def parse_args(argv):
    ap = argparse.ArgumentParser()
    ap.usage = '%(prog)s [options] tests...'
    ap.add_argument('-c', dest='coverage', action='store_true',
                    help='produce coverage information')
    ap.add_argument('-j', metavar='N', type=int, dest='jobs',
                    default=multiprocessing.cpu_count(),
                    help=('run N jobs in parallel [default=%(default)s, '
                          'derived from CPUs available]'))
    ap.add_argument('-n', action='store_true', dest='dry_run',
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
                    help="print time per test (implies -v)")
    ap.add_argument('-v', action='count', dest='verbose', default=0,
                    help="verbose logging")
    ap.add_argument('tests', nargs='*', default=[],
                    help=argparse.SUPPRESS)

    return ap.parse_args(argv)


def run_under_coverage(argv):
    argv = argv or sys.argv
    if '-c' in argv:
        argv.remove('-c')
    if '--coverage' in argv:
        argv.remove('--coverage')
    subprocess.call(['coverage', 'erase'])
    res = subprocess.call(['coverage', 'run', __file__] + argv[1:])
    subprocess.call(['coverage', 'report', '--omit=*/pytest/*'])
    return res


def find_tests(args):
    loader = unittest.loader.TestLoader()
    test_names = []
    for test in args.tests:
        if test.endswith('.py'):
            test = test.replace('/', '').replace('.py', '')
        module_suite = loader.loadTestsFromName(test)
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
            while test_names and len(running_jobs) < args.jobs:
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
    finally:
        pool.close()

    if not args.quiet:
        printer.update('%d tests run in %.4fs, %d failure%s.' %
                       (stats.finished,
                        time.time() - stats.started_time,
                        num_failures,
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
    suite.run(result)
    took = time.time() - start
    if result.failures:
        return 1, result.out, result.err + result.failures[0][1], took
    if result.errors:
        return 1, result.out, result.err + result.errors[0][1], took
    return test_name, 0, result.out, result.err, took


def print_test_started(printer, args, stats, test_name):
    if not args.quiet and printer.should_overwrite:
        printer.update(stats.format() + test_name, elide=(not args.verbose))


def print_test_finished(printer, args, stats, test_name, res, out, err, took):
    suffix = '%s%s%s' % (' failed' if res else ' passed',
                         (' %.4fs' % took) if args.timing else '',
                         (':\n' if (out or err) else ''))
    if res:
        printer.update(stats.format() + test_name + suffix, elide=False)
    elif not args.quiet or out or err:
        printer.update(stats.format() + test_name + suffix,
                       elide=(not out and not err and not args.verbose))
    for l in out.splitlines():
        print_('  %s' % l)
    for l in err.splitlines():
        print_('  %s' % l, stream=sys.stderr)


def print_(msg='', end='\n', stream=sys.stdout):
    stream.write(str(msg) + end)
    stream.flush()


class PassThrough(StringIO.StringIO):
    def __init__(self, stream=None):
        self.stream = stream
        StringIO.StringIO.__init__(self)

    def write(self, *args, **kwargs):
        if self.stream:
            self.stream.write(*args, **kwargs)
        StringIO.StringIO.write(self, *args, **kwargs)

    def flush(self, *args, **kwargs):
        if self.stream:
            self.stream.flush(*args, **kwargs)
        StringIO.StringIO.flush(self, *args, **kwargs)


class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, stream=None, descriptions=None, verbosity=None,
                 pass_through=False):
        self.pass_through = pass_through
        super(TestResult, self).__init__(stream=stream,
                                         descriptions=descriptions,
                                         verbosity=verbosity)
        self.out = ''
        self.err = ''
        self.__orig_out = None
        self.__orig_err = None

    # "Invalid name" pylint: disable=C0103

    def startTest(self, test):
        self.__orig_out = sys.stdout
        self.__orig_err = sys.stderr
        sys.stdout = PassThrough(sys.stdout if self.pass_through else None)
        sys.stderr = PassThrough(sys.stderr if self.pass_through else None)

    def stopTest(self, test):
        self.out = sys.stdout.getvalue()
        self.err = sys.stderr.getvalue()
        sys.stdout = self.__orig_out
        sys.stderr = self.__orig_err


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print >> sys.stderr, "Interrupted, exiting"
        sys.exit(130)
