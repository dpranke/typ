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

import copy
import multiprocessing

try:
    # This gets compatibility for both Python 2 and Python 3.
    # import failure ... pylint: disable=F0401
    from queue import Empty
except ImportError:
    from Queue import Empty


def make_pool(jobs, callback, context, pre_fn, post_fn):
    if jobs > 1:
        return ProcessPool(jobs, callback, context, pre_fn, post_fn)
    return AsyncPool(callback, context, pre_fn, post_fn)


class ProcessPool(object):
    def __init__(self, jobs, callback, context, pre_fn, post_fn):
        self.jobs = jobs
        self.requests = multiprocessing.Queue()
        self.responses = multiprocessing.Queue()
        self.workers = []
        self.closed = False
        for worker_num in range(jobs):
            w = multiprocessing.Process(target=_loop,
                                        args=(worker_num, callback, context,
                                              self.requests, self.responses,
                                              pre_fn, post_fn))
            w.start()
            self.workers.append(w)

    def send(self, msg):
        self.requests.put((True, msg))

    def get(self, block=True, timeout=None):
        return self.responses.get(block, timeout)

    def close(self):
        for _ in self.workers:
            self.requests.put((False, None))
        self.requests.close()
        self.closed = True

    def join(self):
        if not self.closed:
            for w in self.workers:
                w.terminate()
        final_contexts = []
        for w in self.workers:
            final_contexts.append(self.responses.get(True))
            w.join()
        self.responses.close()
        return final_contexts


class AsyncPool(object):
    def __init__(self, callback, context, pre_fn, post_fn):
        self.callback = callback
        self.context = copy.deepcopy(context)
        self.msgs = []
        self.closed = False
        self.post_fn = post_fn
        self.context_after_pre = pre_fn(self.context)
        self.final_context = None

    def send(self, msg):
        self.msgs.append(msg)

    def get(self, block=True, timeout=None):  # unused pylint: disable=W0613
        return self.callback(self.context_after_pre, self.msgs.pop(0))

    def close(self):
        self.closed = True
        self.final_context = self.post_fn(self.context_after_pre)

    def join(self):
        return [self.final_context]


def _loop(_worker_num, callback, context, requests, responses, setup_process,
          teardown_process):
    try:
        context_after_pre = setup_process(context)
        keep_going = True
        while keep_going:
            keep_going, args = requests.get(block=True)
            if keep_going:
                resp = callback(context_after_pre, args)
                responses.put(resp)
    except Empty:
        pass
    except IOError:
        pass
    finally:
        responses.put(teardown_process(context_after_pre))
