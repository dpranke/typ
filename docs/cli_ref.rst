TYP: Command Line Overview and Examples
=======================================

Contents
--------

* Overview
* Sample test repo
* Basic usage
* Invoking typ
* Controlling output
* Selecting which tests to run
* Code coverage
* Uploading test results

Overview
--------

``typ`` is primarily designed to test Python code. The driving goal is
to provide a more user-friendly face to the ``unittest`` framework: the
output is more regular and concise, spurious output is filtered by default,
and tests are run in parallel.

The basic idea is that typ should Just Work and do what you want it to do
without needing a lot of explicit instructions.

Sample test repo
----

For what follows, let's assume we have the following simple Python project
(mirrored from
`typ's examples/ directory <https://github.com/dpranke/typ/examples>`_::

    % find hello -mindepth 1
    hello/__init__.py
    hello/__main__.py
    hello/greetings
    hello/greetings/__init__.py
    hello/greetings/greetings.py
    hello/greetings/greetings_test.py
    hello/hello.py
    hello/hello_test.py
    hello/places.py
    hello/places_test.py
    % python -m hello
    hello, world
    %


Basic usage
----

Invoking typ
----


Controlling output
----

Selecting which tests to run
----

Code coverage
----

Uploading test results
----


