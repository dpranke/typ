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

from typ import test_case


class TestFuncs(test_case.MainTestCase):

    def test_convert_newlines(self):
        cn = test_case.convert_newlines
        self.assertEqual(cn('foo'), 'foo')
        self.assertEqual(cn('foo\nbar\nbaz'), 'foo\nbar\nbaz')
        self.assertEqual(cn('foo\rbar\nbaz\r'), 'foo\nbar\nbaz\n')
        self.assertEqual(cn('foo\r\nbar\r\nbaz\r\nmeh\n'),
                         'foo\nbar\nbaz\nmeh\n')


class TestMainTestCase(test_case.MainTestCase):

    def test_basic(self):
        h = self.make_host()
        files = {
            'test.py': """
import os
import sys
print "in:", sys.stdin.read()
print "out:", os.environ['TEST_VAR']
print >>sys.stderr, "err"
with open("../results", "w") as fp:
  fp.write(open("../input").read() + " written")
""",
            'input': 'results',
            'subdir/x': 'y',
        }
        exp_files = files.copy()
        exp_files['results'] = 'results written'
        self.check(prog=[h.python_interpreter, '../test.py'],
                   stdin='hello on stdin',
                   env={'TEST_VAR': 'foo'},
                   cwd='subdir',
                   files=files,
                   ret=0, out='in: hello on stdin\nout: foo\n',
                   err='err\n', exp_files=exp_files)
