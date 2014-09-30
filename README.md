typ (Test Your Program)
=======================

typ is a simple program for testing command line executables and Python code.

Introduction
------------

typ originated out of work on the Blink and Chromium projects, as a way to 
provide a friendly interface on top of the Python unittest modules.

It supports test discovery, parallel test execution,
clean logging of progress and results in the style of the Ninja build tool,

When testing Python code it also supports integrated code coverage reporting
and debugging (pdb) support.

Work remaining
--------------

typ is still a work in progress, but it's getting close to being done.
Things remaining for 1.0, roughly in priority order:

- Testing intra-method test skipping (a la @unittest.skip) and 
  expected failures
- Clean up the API and refactor the tester module
- Support for per-process setup and teardown entry points (for telemetry
  and run-webkit-tests to support efficient per-process launching of
  browsers)
- (Re-)test on Windows, Linux to check for regressions
- Add more testing of the exact output
- Remove as many of the "pragma: no-cover" hacks as possible and get test
  coverage for the remaining blocks of "uncovered" code:
  - figure out how to get coverage of the command-line based tests
  - figure out how to get output trapping working inside tests
  - add fakes for coverage and pdb
  - test tests failing a second time
  - test failing uploads
- Write documentation
- Write tests for different configurations:
  - typ not installed, invoked via typ/main.py
  - typ not installed, invoked via -m typ in dir above typ
  - typ installed, invoked via typ/main.py
  - test running tests with absolute paths to test files

Possible future work
--------------------

- investigate unittest.TestResult.buffer
- support testing javascript, c++/gtest-style binaries
- Implement a non-python file format for testing command line interfaces
- Support for test sharding in addition to parallel execution (so that
  run-webkit-tests can re-use as much of the code as possible
- Support for non-unittest runtest invocation (for run-webkit-tests,
  other harnesses?)
