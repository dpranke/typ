import os
import sys

from typ import test_case

path_to_main = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'main.py')

class TestScript(test_case.MainTestCase):
    prog = [sys.executable, path_to_main]

    def test_none(self):
        self.check([], ret=0, out='Hello, world.\n')

    def test_you(self):
        self.check(['Good-bye', 'you'], ret=0, out='Good-bye, you.\n')


class TestModule(TestScript):
    in_place = True
    prog = [sys.executable, '-m', 'hello']

class TestInline(TestScript):
    prog = []

    def func(self, host, argv):
        from hello import main
        return main.main(argv)
