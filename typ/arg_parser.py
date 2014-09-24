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

from typ.host import Host


class _Bailout(Exception):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        self._host = kwargs['host']
        del kwargs['host']
        super(ArgumentParser, self).__init__(*args, **kwargs)

        self.exit_status = None
        self.exit_message = None

        self.usage = '%(prog)s [options] [tests...]'
        self.add_argument('--builder-name',
                          help=('Builder name to include in the '
                                'uploaded data.'))
        self.add_argument('-c', '--coverage', action='store_true',
                          help='produce coverage information')
        self.add_argument('--coverage-omit', default=None,
                          help='globs to omit in coverage report')
        self.add_argument('-d', '--debugger', action='store_true',
                          help='run a single test under the debugger')
        self.add_argument('-n', '--dry-run', action='store_true',
                          help=('Do not actually run the tests, act like they '
                                'succeeded.'))
        self.add_argument('-f', '--file-list', metavar='FILENAME',
                          action='store',
                          help=('Take the list of tests from the file '
                                '(use "-" for stdin).'))
        self.add_argument('--isolate', metavar='glob', default=[],
                          action='append',
                          help='test globs to run serially (in isolation)')
        self.add_argument('-j', '--jobs', metavar='N', type=int,
                          default=0,
                          help=('Run N jobs in parallel (0 gives CPUs '
                                'available).'))
        self.add_argument('-l', '--list-only', action='store_true',
                          help=('List all the test names found in the given '
                               'tests.'))
        self.add_argument('--master-name',
                          help=('Buildbot master name to include in the '
                                'uploaded data.'))
        self.add_argument('--metadata', action='append', default=[],
                          help=('Optional key=value metadata that will be '
                                'included in the results.'))
        self.add_argument('--no-trapping', action='store_true',
                          help=argparse.SUPPRESS)
        self.add_argument('-p', '--passthrough', action='store_true',
                          help='Pass output through while running tests.')
        self.add_argument('-P', '--path', action='append', default=[],
                          help='add dir to sys.path')
        self.add_argument('-q', '--quiet', action='store_true', default=False,
                          help='Be as quiet as possible (only print errors).')
        self.add_argument('--retry-limit', type=int, default=0,
                          help='Retry each failure up to N times.')
        self.add_argument('-s', '--status-format',
                          help=('Format for status updates '
                                '(uses NINJA_STATUS env var if set). '))
        self.add_argument('--skip', metavar='glob', default=[],
                          action='append',
                          help='test globs to skip')
        self.add_argument('--suffixes', metavar='glob', default=[],
                          action='append',
                          help='filename globs to look for')
        self.add_argument('--terminal-width', type=int, default=0,
                          help=('Width of output (current terminal width '
                                'if available.'))
        self.add_argument('--test-results-server',
                          help=('If specified, upload the full results to '
                                'this server.'))
        self.add_argument('--test-type',
                          help=('Name of test type to include in the uploaded '
                                'data (e.g., "telemetry_unittests").'))
        self.add_argument('-t', '--timing', action='store_true',
                          help='Print timing info.')
        self.add_argument('--top-level-dir', default=None,
                          help=('Top directory of project '
                                '(used when running subdirs).'))
        self.add_argument('--write-full-results-to', metavar='FILENAME',
                          action='store',
                          help=('If specified, write the full results to '
                               'that path.'))
        self.add_argument('-v', '--verbose', action='count', default=0,
                          help=('Log verbosely '
                                '(specify multiple times for more output).'))
        self.add_argument('-V', '--version', action='store_true',
                          help='Print the typ version and exit.')
        self.add_argument('tests', nargs='*', default=[],
                          help=argparse.SUPPRESS)

    def parse_args(self, args=None, namespace=None):
        try:
            super(ArgumentParser, self).parse_args(args=args,
                                                   namespace=namespace)
        except _Bailout:
            pass

    def _print_message(self, msg, file=None):
        self._host.print_(msg=msg, stream=file, end='')

    def print_usage(self, file=None):
        self._print_message(self.format_usage(), file=file)

    def print_help(self, file=None):
        self._print_message(msg=self.format_help(), file=file)

    def error(self, message):
        self.exit(2, '%s: error: %s\n' % (self.prog, message))

    def exit(self, status=0, message=None):
        self.exit_status = status
        if message:
            self._print_message(message, file=self._host.stderr)
        raise _Bailout()
