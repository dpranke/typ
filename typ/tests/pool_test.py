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

from typ import pool as typ_pool

def setup_fn(usrp):
    usrp['setup'] = True

def teardown_fn(usrp):
    usrp['teardown'] = True

def echo_fn(usrp, args):
    return '%s/%s/%s' % (usrp['setup'], usrp['teardown'], args)

class TestPool(unittest.TestCase):

    def run_basic_test(self, jobs):
        usrp = {'setup': False, 'teardown': False}
        pool = typ_pool.make_pool(jobs, echo_fn, usrp, setup_fn, teardown_fn)
        pool.send('hello')
        pool.send('world')
        msg1 = pool.get()
        msg2 = pool.get()
        pool.close()
        pool.join()
        self.assertEqual(set([msg1, msg2]),
                         set(['True/False/hello',
                              'True/False/world']))

    def test_single_job(self):
        self.run_basic_test(1)

    def test_two_jobs(self):
        self.run_basic_test(2)
