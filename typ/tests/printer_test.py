# Copyright 2014 Dirk Pranke. All rights reserved.
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

import unittest

from printer import Printer


class TestPrinter(unittest.TestCase):
    def setUp(self):
        # 'Invalid name' pylint: disable=C0103
        self.out = []

    def print_(self, msg, end='\n'):
        self.out.append(msg + end)

    def test_basic(self):
        pr = Printer(self.print_, False)
        pr.update('foo')
        pr.flush()
        self.assertEqual(self.out, ['foo', '\n'])

    def test_elide(self):
        pr = Printer(self.print_, False, cols=8)
        pr.update('hello world')
        pr.flush()
        self.assertEqual(self.out, ['hel ...', '\n'])

    def test_overwrite(self):
        pr = Printer(self.print_, True)
        pr.update('hello world')
        pr.update('goodbye world')
        pr.flush()
        self.assertEqual(self.out,
                         ['hello world',
                          '\r           \r',
                          'goodbye world',
                          '\n'])
