
class Printer(object):
    def __init__(self, print_, should_overwrite, cols=80):
        self.print_ = print_
        self.should_overwrite = should_overwrite
        self.cols = cols
        self.last_line = ''

    def flush(self):
        if self.last_line:
            self.print_('')
            self.last_line = ''

    def update(self, msg, elide=True):
        if elide and len(msg) > self.cols - 5:
            msg = msg[:self.cols - 5] + ' ...'
        if self.should_overwrite:
            self.print_('\r' + ' ' * len(self.last_line) + '\r', end='')
        elif self.last_line:
            self.print_('')
        self.print_(msg, end='')
        last_nl = msg.rfind('\n')
        self.last_line = msg[last_nl + 1:]
