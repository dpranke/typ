# Copyright (c) 2018 Yandex LLC. All rights reserved.
# Author: Kirill Kosarev <kirr@yandex-team.ru>

from collections import namedtuple
import multiprocessing
import os
import Queue
import signal
import threading
import time
import traceback

from typ.host import Host


UPDATE_DELAY = 0.1
PROCESS_TERMINATION_WAIT_TIME = 3


Task = namedtuple('Task', ['task_id', 'worker_id', 'pid', 'start_time',
                           'timeout', 'args'])

Worker = namedtuple('Worker', ['worker_id', 'terminate_lock', 'proc'])


def _timed_out(task, now, default_timeout):
    return now - task.start_time > (default_timeout if task.timeout is None
                                    else task.timeout)


class _MessageType(object):
    Request = 'Request'
    Close = 'Close'
    Done = 'Done'
    Error = 'Error'
    Interrupt = 'Interrupt'

    Timeout = 'Timeout'
    Started = 'Started'
    Finished = 'Finished'


def _raise_on_error(msg_type, msg):
    if msg_type == _MessageType.Error:
        worker_num, tb = msg
        raise Exception("Error from worker %d (traceback follows):\n%s" %
                        (worker_num, tb))
    elif msg_type == _MessageType.Interrupt:
        raise KeyboardInterrupt


class LockedQueue(object):
    def __init__(self, queue, lock):
        self.queue = queue
        self.lock = lock

    def put(self, *args, **kwargs):
        with self.lock:
            return self.queue.put(*args, **kwargs)

    def get(self, *args, **kwargs):
        with self.lock:
            return self.queue.get(*args, **kwargs)


class PoolManager(object):
    def __init__(self, host, jobs, timeout, callback, context, pre_fn, post_fn,
                 requests_queue, response_writer):
        self.timeout = timeout
        self.workers = []
        self.num_workers = 0
        self.pre_fn = pre_fn
        self.post_fn = post_fn
        self.callback = callback
        self.initial_context = context
        self.jobs = jobs
        self.host = host
        self.closed = False

        self.response_writer = response_writer
        self.requests_queue = requests_queue
        self.watchdog_queue = multiprocessing.Queue()

        for worker_num in range(jobs):
            self._start_worker()

        self.last_check_time = time.time()
        self.watchdog_thread = threading.Thread(
            target=self._watchdog_thread_loop)
        self.watchdog_thread.start()

    def _start_worker(self):
        self.num_workers += 1
        terminate_lock = multiprocessing.RLock()
        w = multiprocessing.Process(
            target=_worker_loop, args=(
                self.requests_queue,  self.watchdog_queue, self.host.for_mp(),
                terminate_lock, self.num_workers, self.callback,
                self.initial_context, self.pre_fn, self.post_fn))
        w.start()
        self.workers.append(Worker(self.num_workers, terminate_lock, w))

    # |_stop_watchdog_thread()| must be always invoked before killing
    # processes
    def _stop_watchdog_thread(self):
        if not self.closed:
            self.closed = True
            self.watchdog_thread.join()

    # Could be used from other thread.
    def close(self):
        self._stop_watchdog_thread()
        for _ in self.workers:
            self.requests_queue.put((_MessageType.Close, None, None))

    def join(self):
        if not self.closed:
            self._stop_watchdog_thread()
            for w in self.workers:
                w.proc.terminate()
                w.proc.join()
            return []

        for w in self.workers:
            w.proc.join()

        final_responses = []
        done_messages = 0
        while done_messages < self.jobs:
            msg_type, resp = self.watchdog_queue.get()
            _raise_on_error(msg_type, resp)
            if msg_type == _MessageType.Done:
                final_responses.append(resp[1])
                done_messages += 1

        return final_responses

    def _check_for_timeouts(self, active_tasks):
        if not self.timeout:
            return

        now = time.time()
        if now - self.last_check_time < UPDATE_DELAY:
            return

        timeout_tasks = [t for t in active_tasks
                         if _timed_out(t, now, self.timeout)]
        for task in timeout_tasks:
            worker = next((w for w in self.workers
                           if w.worker_id == task.worker_id), None)
            # |worker| could be none if it was already terminated by task
            # timeout but 'Timeout' message still not processed.
            if worker is None:
                continue
            with worker.terminate_lock:
                worker.proc.terminate()
                worker.proc.join(PROCESS_TERMINATION_WAIT_TIME)
                if worker.proc.is_alive():
                    raise RuntimeError(
                        'Unable to terminate worker: %d task: %d',
                        worker.worker_id, task.task_id)
                else:
                    self.workers.remove(worker)

        new_workers = self.jobs - len(self.workers)
        for i in range(new_workers):
            self._start_worker()

    def _watchdog_thread_loop(self):
        active_tasks = []
        try:
            while not self.closed:
                while True:
                    try:
                        msg, data = self.watchdog_queue.get(
                            block=True, timeout=UPDATE_DELAY)
                    except Queue.Empty:
                        break
                    if msg == _MessageType.Started:
                        active_tasks.append(data)
                    else:
                        if msg in (_MessageType.Finished,
                                   _MessageType.Timeout):
                            task_id = data[0].task_id
                            task = next((t for t in active_tasks
                                         if t.task_id == task_id))
                            active_tasks.remove(task)
                        self.response_writer.send((msg, data))
                    self._check_for_timeouts(active_tasks)
                self._check_for_timeouts(active_tasks)
        except Exception as e:
            self.response_writer.send((_MessageType.Error,
                                       (0, traceback.format_exc(e))))


class ProcessPoolWithTimeouts(object):
    def __init__(self, host, jobs, timeout,
                 callback, timeout_fn,
                 context, pre_fn, post_fn):
        response_reader, response_writer = multiprocessing.Pipe(False)
        self.response_reader = response_reader
        self.requests_queue = multiprocessing.Queue()
        self.task_id = 0
        self.timeout_fn = timeout_fn
        self.pool_manager = PoolManager(
            host, jobs, timeout, callback, context, pre_fn, post_fn,
            self.requests_queue, response_writer)

    def send(self, msg):
        self.task_id += 1
        self.requests_queue.put((_MessageType.Request, self.task_id, msg))

    def get(self):
        msg_type, resp = self.response_reader.recv()
        _raise_on_error(msg_type, resp)
        if msg_type == _MessageType.Timeout:
            task, stack_trace = resp
            res = self.timeout_fn(
                task.args, task.worker_id, task.pid,
                task.start_time, stack_trace)
        else:
            assert msg_type == _MessageType.Finished
            res = resp[1]
        return res

    def close(self):
        self.pool_manager.close()

    def join(self):
        return self.pool_manager.join()


def _sigterm_handler(queue, task, sig, stack_frame):
    stack = '\n'.join(traceback.format_stack(stack_frame))
    queue.put((_MessageType.Timeout, (task, stack)))
    queue.close()
    queue.join_thread()
    os._exit(signal.SIGTERM)


def _worker_loop(requests, watchdog_queue,
                 host, terminate_lock, worker_num,
                 callback, context, pre_fn, post_fn):
    host = host or Host()
    requests = LockedQueue(requests, terminate_lock)
    watchdog_queue = LockedQueue(watchdog_queue, terminate_lock)
    try:
        context_after_pre = pre_fn(host, worker_num, context)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        while True:
            message_type, task_id, args = requests.get()
            if message_type == _MessageType.Close:
                resp = post_fn(context_after_pre)
                watchdog_queue.put((_MessageType.Done, (worker_num, resp)))
                break
            assert message_type == _MessageType.Request
            task = Task(task_id, worker_num, os.getpid(),
                        time.time(), args.timeout, args)
            signal.signal(
                signal.SIGTERM,
                lambda sig, frame: _sigterm_handler(watchdog_queue.queue, task,
                                                    sig, frame))

            watchdog_queue.put((_MessageType.Started, task))
            resp = callback(context_after_pre, args)

            watchdog_queue.put((_MessageType.Finished, (task, resp)))
    except KeyboardInterrupt as e:
        watchdog_queue.put((_MessageType.Interrupt, (worker_num, str(e))))
    except Exception as e:
        watchdog_queue.put((_MessageType.Error,
                            (worker_num, traceback.format_exc(e))))
