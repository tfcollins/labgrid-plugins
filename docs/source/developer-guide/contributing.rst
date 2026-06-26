Contributing
============

.. tip::

   New to the project? Start with :doc:`onboarding` — it walks through the dev environment,
   the ``nox`` loop, how plugins register, and how to add a component. This page is the
   condensed command reference.

Development Setup
-----------------

Install development dependencies::

    uv venv venv --python 3.10
    source venv/bin/activate
    uv pip install -e ".[dev,docs]"

Running Tests
-------------

Run all tests::

    pytest tests/

Linting and Formatting
-----------------------

Check code style::

    ruff check adi_lg_plugins/ tests/

Auto-fix issues::

    ruff check --fix adi_lg_plugins/ tests/

Format code::

    ruff format adi_lg_plugins/ tests/

Building Documentation
----------------------

Build HTML documentation::

    cd docs
    make html
