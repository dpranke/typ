import unittest

from hello import greetings


class TestGreetingLookup(unittest.TestCase):
    def test_none(self):
        self.assertEqual(greetings.lookup(), "Hello")

    def test_you(self):
        self.assertEqual(greetings.lookup("Seeya"), "Seeya")
