import unittest

from hello import nouns


class TestNounLookup(unittest.TestCase):
    def test_none(self):
        self.assertEqual(nouns.lookup(), "world")

    def test_you(self):
        self.assertEqual(nouns.lookup("you"), "you")
