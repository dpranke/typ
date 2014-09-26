#!/usr/bin/env python

import sys

from subprocess import call


def print_(msg, end='\n', stream=sys.stdout):
    stream.write(msg + end)


def usage():
    print_("""\
usage: go COMMAND

Where COMMAND is one of:
  build     build an installable package
  check     runs lint, build, cover
  clean     remove any derived objects
  cover     run test coverage
  develop   install a 'developable' package
  install   install a complete package
  lint      run lint over the osurce
  pull      pull latest sources from repo
  push      push latest sources from repo
  test      run tests""")


def main(argv):
    if len(argv) != 1 or argv[0] in ('-h', '--help', 'help'):
        usage()
        return 2

    return run(argv[0])


def run(cmd):
    if cmd == 'build':
        return call([sys.executable, 'setup.py', 'build', '--quiet'])
    if cmd == 'check':
        ret = run('lint')
        if not ret:
            ret = run('build')
        if not ret:
            ret = run('cover')
        return ret
    if cmd == 'cover':
        ret = call(['coverage', 'erase'])
        if not ret:
            ret = call(['coverage', 'run', '-m', 'typ', '-j', '1'])
        if not ret:
            ret = call(['coverage', 'report', '--omit', '*/site-packages/*'])
        return ret
    if cmd == 'develop':
        ret = call([sys.executable, 'setup.py', 'develop'])
    if cmd == 'install':
        ret = call([sys.executable, 'setup.py', 'install'])
    if cmd == 'lint':
        return call('pylint --rcfile=pylintrc */*.py */*/*.py', shell=True)
    if cmd == 'install':
        return call([sys.executable, 'setup.py', 'install'])
    if cmd == 'pull':
        return call(['git', 'pull'])
    if cmd == 'push':
        return call(['git', 'push'])
    if cmd == 'test':
        return call([sys.executable, '-m', 'typ'])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
