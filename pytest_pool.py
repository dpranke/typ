import multiprocessing
import Queue


Empty = Queue.Empty  # "Invalid name" # pylint: disable=C0103


def make_pool(jobs, callback, usrp):
    if jobs > 1:
        return ProcessPool(jobs, callback, usrp)
    return AsyncPool(callback, usrp)


class ProcessPool(object):
    def __init__(self, jobs, callback, usrp):
        self.jobs = jobs
        self.requests = multiprocessing.Queue()
        self.responses = multiprocessing.Queue()
        self.workers = []
        for worker_num in range(jobs):
            w = multiprocessing.Process(target=_loop,
                                        args=(worker_num, callback, usrp,
                                              self.requests, self.responses))
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

    def terminate(self):
        for w in self.workers:
            w.terminate()
        self.responses.close()

    def join(self):
        for w in self.workers:
            w.join()


class AsyncPool(object):
    def __init__(self, callback, usrp):
        self.callback = callback
        self.usrp = usrp
        self.msgs = []

    def send(self, msg):
        self.msgs.append(msg)

    def get(self, block=True, timeout=None): # unused pylint: disable=W0613
        return self.callback(self.usrp, self.msgs.pop(0))

    def close(self):
        pass

    def terminate(self):
        pass

    def join(self):
        pass


def _loop(_worker_num, callback, usrp, requests, responses):
    try:
        keep_going = True
        while keep_going:
            keep_going, args = requests.get(block=True)
            if keep_going:
                resp = callback(usrp, args)
                responses.put(resp)
    except Queue.Empty:
        pass
