TYP: Test Your (Python) Project
===============================

``typ`` is a simple framework for testing command line executables and Python
code.

Contents
--------

* Overview and Features.

* `Command line overview and examples <cli_overview.rst>`_.

* `Command line reference <cli_ref.rst>`_.

* `API overview and examples <api_overview.rst>`_.

* `API reference <api_ref.rst>`_.

Overview
--------

When testing Python code, ``typ`` is basically a wrapper around the standard
``unittest`` module, but it provides the following bits of additional
functionality:

* Parallel test execution.

* Clean output in the style of the 
  `Ninja build tool <https://martine.github.io/ninja/>`_.

* A more flexible mechanism for discovering tests from the
  command line and controlling how they are run:

  * Support for importing tests by directory, filename, or module.
  * Support for specifying tests to skip, tests to run in parallel,
    and tests that need to be run by themselves

* Support for producing traces of test times compatible with `Chrome's
  tracing infrastructure <https://google.github.io/trace-viewer>`_.

* Integrated test coverage reporting (including parallel coverage).

* Integrated support for debugging tests.

* Support for uploading test results automatically to a server (this is
  useful for monitoring the results of continuous integration tests).

* Simple libraries for integrating Ninja-style statistics and line
  printing into your own code (the Stats and Printer classes).

* Support for processing arbitrary arguments from calling code to
  test cases.

* Support for once-per-process setup and teardown hooks.

(These last two bullet points allow one to write tests that do not require
Python globals).
