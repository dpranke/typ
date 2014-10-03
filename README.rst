typ (Test Your Program)
=======================
typ is a simple program for testing command line executables and Python code.

When testing Python code, it is basically a wrapper around the standard
unittest module, but it provides the following bits of additional
functionality:

* Parallel test execution.
* Clean output in the style of the Ninja build tool.
* A more flexible mechanism for discovering tests from the
  command line and controlling how they are run:

  * Support for importing tests by directory, filename, or module.
  * Support for specifying tests to skip, tests to run in parallel,
    and tests that need to be run by themselves

* Support for producing traces of test times compatible with Chrome's
  tracing infrastructure (trace_viewer).
* Integrated test coverage reporting.
* Integrated support for debugging tests.
* Support for uploading test results automatically to a server
  (useful for continuous integration monitoring of test results).
* An abstraction of operating system functionality called the
  Host class. This can be used by other python code to write more
  portable and easily testable code by wrapping the multiprocessing,
  os, subprocess, and time modules.
* Simple libraries for integrating Ninja-style statistics and line
  printing into your own code (the Stats and Printer classes).
* Support for processing arbitrary arguments from calling code to
  test cases.
* Support for once-per-process setup and teardown hooks.

(These last two bullet points allow one to write tests that do not require
Python globals).

History
-------

typ originated out of work on the Blink and Chromium projects, as a way to
provide a friendly interface on top of the Python unittest modules.

Work remaining
--------------

typ is still a work in progress, but it's getting close to being done.
Things remaining for 1.0, roughly in priority order:

- Handling failed module imports more cleanly (catch syntax errors better,
  etc.).
- Change coverage reporting to only include stuff under top_level_dir
  by default (and to include all files, including uncovered/unimported ones).
- Add input validation on all of the public APIs.
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

- Implement a non-python file format for testing command line interfaces,
  clean up testing of exe's.

Possible future work
--------------------

- Support testing javascript, c++/gtest-style binaries.
- Support for test sharding in addition to parallel execution (so that
  run-webkit-tests can re-use as much of the code as possible.
- Support for non-unittest runtest invocation (for run-webkit-tests,
  other harnesses?)
