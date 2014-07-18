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

import sys
import unittest


def print_(msg='', end='\n', stream=sys.stdout):
    stream.write(str(msg) + end)
    stream.flush()


class FailingTests(unittest.TestCase):
    def test_fail(self):
        self.fail('This should fail.')

    def test_prints_to_stdout_and_fails(self):
        print_('hello, stdout')
        self.fail('This should fail.')

    def test_prints_to_stderr_and_fails(self):
        print_('hello, stderr', stream=sys.stderr)
        self.fail('This should fail.')

