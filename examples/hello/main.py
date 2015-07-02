from __future__ import print_function

import argparse
import os
import sys

# We need this to ensure that hello can be invoked directly.
pardir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if not pardir in sys.path:  # pragma: no cover
    sys.path.append(pardir)

from hello import greetings
from hello import nouns


def greet(greeting, noun):
    return "%s, %s." % (greetings.lookup(greeting), nouns.lookup(noun))


def main(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('greeting', nargs='?')
    parser.add_argument('noun', nargs='?')
    args = parser.parse_args(args)
    print(greet(args.greeting, args.noun))
    return 0

if __name__ == '__main__':  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
