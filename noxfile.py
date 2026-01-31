import nox

# Define default sessions
nox.options.sessions = ["lint", "tests", "docs"]
nox.options.default_venv_backend = "uv"


@nox.session
def tests(session):
    """Run tests."""
    # Install the package in editable mode with dev dependencies
    session.install("-e", ".[dev]")
    # Run pytest
    session.run("pytest", *session.posargs)


@nox.session
def lint(session):
    """Run linting and style checks."""
    session.install("ruff")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session
def format(session):
    """Run formatters and auto-fixers."""
    session.install("ruff")
    session.run("ruff", "format", ".")
    session.run("ruff", "check", "--fix", ".")


@nox.session
def docs(session):
    """Build the documentation."""
    session.install("-e", ".[docs]")
    # Build the documentation using sphinx-build directly
    session.run("sphinx-build", "-b", "html", "docs/source", "docs/build/html")
