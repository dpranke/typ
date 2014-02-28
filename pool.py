import multiprocessing
import Queue


class Pool(object):
    def __init__(self, num_processes, callback):
        self.num_processes = num_processes
        self.callback = callback
        self.requests = multiprocessing.Queue()
        self.responses = multiprocessing.Queue()
        self.workers = []
        for worker_num in range(num_processes):
            w = multiprocessing.Process(target=_loop,
                                        args=(worker_num, callback, self.requests,
                                              self.responses))
            w.start()
            self.workers.append(w)

    def send(self, msg):
        self.requests.put(msg)

    def get(self, block=True, timeout=None):
        return self.responses.get(block, timeout)

    def close(self):
        self.requests.close()

    def terminate(self):
        for w in self.workers:
            w.terminate()
        self.responses.close()

    def join(self):
        for w in self.workers:
            w.join()


def _loop(worker_num, callback, requests, responses):
    try:
        while True:
            args = requests.get(block=True)
            resp = callback(args)
            responses.put(resp)
    except Queue.Empty:
        pass
