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
from typ.host import Host
from typ.pool import make_pool, ProcessPool, _loop


def setup_fn(host, worker_num, context):  # pylint: disable=W0613
    context['setup'] = True
    return context


def teardown_fn(context):
    context['teardown'] = True
    return context


def echo_fn(context, msg):
    return '%s/%s/%s' % (context['setup'], context['teardown'], msg)


class TestPool(test_case.TestCase):

    def run_basic_test(self, jobs):
        host = Host()
        context = {'setup': False, 'teardown': False}
        pool = make_pool(host, jobs, echo_fn, context, setup_fn, teardown_fn)
        pool.send('hello')
        pool.send('world')
        msg1 = pool.get()
        msg2 = pool.get()
        pool.close()
        final_contexts = pool.join()
        self.assertEqual(set([msg1, msg2]),
                         set(['True/False/hello',
                              'True/False/world']))
        expected_context = {'setup': True, 'teardown': True}
        expected_final_contexts = [expected_context for _ in range(jobs)]
        self.assertEqual(final_contexts, expected_final_contexts)

    def test_loop(self):
        host = Host()
        jobs = 0
        context = {'setup': False, 'teardown': False}
        pool = ProcessPool(host, jobs, echo_fn, context, setup_fn, teardown_fn)
        pool.send('hello')

        worker_num = 1
        _loop(pool.requests, pool.responses, host, worker_num, echo_fn,
              context, setup_fn, teardown_fn, should_loop=False)
        resp = pool.get()
        self.assertEqual(resp, 'True/False/hello')
        pool.close()
        pool.join()

    def test_pickling_errors(self):
        def unpicklable_fn():  # pragma: no cover
            pass

        host = Host()
        jobs = 2
        self.assertRaises(ValueError, make_pool,
                          host, jobs, echo_fn, unpicklable_fn, None, None)
        self.assertRaises(ValueError, make_pool,
                          host, jobs, echo_fn, None, unpicklable_fn, None)
        self.assertRaises(ValueError, make_pool,
                          host, jobs, echo_fn, None, None, unpicklable_fn)

    def test_single_job(self):
        self.run_basic_test(1)

    def test_two_jobs(self):
        self.run_basic_test(2)

    def test_no_close(self):
        host = Host()
        context = {'setup': False, 'teardown': False}
        pool = make_pool(host, 2, echo_fn, context, setup_fn, teardown_fn)
        final_contexts = pool.join()
        self.assertEqual(final_contexts, [])
