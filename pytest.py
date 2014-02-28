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

    printer = Printer(print_out, sys.stdout.isatty() and not args.verbose)

    stats.total = len(test_names)
    for name in test_names:
        stats.started += 1
        printer.update(stats.format() + name, elide=(args.verbose == 0))
        res, out, err = run_test(name)
        stats.finished += 1
        printer.update(stats.format() + name + ' passed' if res == 0 else ' failed:',
                       elide=(args.verbose == 0 and res == 0))
        for l in out.splitlines():
            print '  %s' % l
        for l in err.splitlines():
            print >> sys.stderr, '  %s' % l
    print ''

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
