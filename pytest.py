import argparse
import multiprocessing
import os
import sys
import time
import unittest
import StringIO


from stats import Stats
from printer import Printer
from pool import Pool

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.usage = '%(prog)s [options] tests...'
    ap.add_argument('-j', metavar='N', type=int, dest='jobs',
                    default=multiprocessing.cpu_count(),
                    help=('run N jobs in parallel [default=%(default)s, '
                          'derived from CPUs available]'))
    ap.add_argument('-n', action='store_true', dest='dry_run',
                    help=('dry run (don\'t run commands but act like they '
                          'succeeded)'))
    ap.add_argument('-q', action='store_true', dest='quiet', default=False,
                    help='be quiet (only print errors)')
    ap.add_argument('-v', action='count', dest='verbose', default=0)
    ap.add_argument('tests', nargs='*', default=[],
                    help=argparse.SUPPRESS)

    args = ap.parse_args(argv)

    started_time = time.time()

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

    stats = Stats(os.getenv('NINJA_STATUS', '[%s/%t] '), time.time,
                  started_time)

    def print_out(msg, end='\n'):
        sys.stdout.write(str(msg) + end)
        sys.stdout.flush()

    should_overwrite = sys.stdout.isatty() and not args.verbose
    printer = Printer(print_out, should_overwrite)

    stats.total = len(test_names)
    printed_something = False
    returncode = 0
    for name in test_names:
        stats.started += 1
        if not args.quiet and should_overwrite:
            printer.update(stats.format() + name, elide=(not args.verbose))

        res, out, err = run_test(name)

        stats.finished += 1
        if res:
            returncode = 1
            suffix = ' failed' + (':' if (out or err) else '')
            printer.update(stats.format() + name + suffix, elide=False)
        elif not args.quiet or out or err:
            suffix = ' passed' + (':' if (out or err) else '')
            printer.update(stats.format() + name + suffix,
                           elide=(not out and not err))
        for l in out.splitlines():
            print '  %s' % l
        for l in err.splitlines():
            print >> sys.stderr, '  %s' % l

    if not args.quiet or returncode:
        print ''
    return returncode

def run_test(name):
    loader = unittest.loader.TestLoader()
    result = TestResult()
    suite = loader.loadTestsFromName(name)
    suite.run(result)
    if result.failures:
        return 1, result.out, result.err + result.failures[0][1]
    if result.errors:
        return 1, result.out, result.err + result.errors[0][1]
    return 0, result.out, result.err


class TestResult(unittest.TestResult):
    # unittests's TestResult has built-in support for buffering
    # stdout and stderr, but unfortunately it interacts awkwardly w/
    # the way they format errors (the output gets comingled and rearranged).
    def __init__(self, *args, **kwargs):
        super(TestResult, self).__init__(*args, **kwargs)
        self.out = ''
        self.err = ''

    def startTest(self, test):
        self.__orig_out = sys.stdout
        self.__orig_err = sys.stderr
        sys.stdout = StringIO.StringIO()
        sys.stderr = StringIO.StringIO()

    def stopTest(self, test):
        self.out = sys.stdout.getvalue()
        self.err = sys.stderr.getvalue()
        sys.stdout = self.__orig_out
        sys.stderr = self.__orig_err

if __name__ == '__main__':
    main()
