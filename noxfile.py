import nox

# Define default sessions
## `typecheck` is opt-in (`nox -s typecheck`) until the baseline is cleaned;
## running `nox` with no args should not fail on pre-existing diagnostics.
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
def typecheck(session):
    """Run ty static type checker."""
    # Install the package + deps so ty can resolve third-party imports.
    session.install("-e", ".[dev]")
    # Point ty at the session's own virtualenv.
    session.run("ty", "check", "--python", session.virtualenv.location, *session.posargs)


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


@nox.session(venv_backend="none")
def lint_pins(session):
    """Fail if any consumer-facing example pins != RECOMMENDED_PIN (or uses @main)."""
    from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN
    from adi_lg_plugins.hw_ci.pin_lint import CONSUMER_PIN_PATHS, find_consumer_pin_violations

    violations = find_consumer_pin_violations(CONSUMER_PIN_PATHS, RECOMMENDED_PIN)
    for f, line, found in violations:
        session.log(f"{f}:{line}: consumer pin @{found} != @{RECOMMENDED_PIN}")
    if violations:
        session.error(f"{len(violations)} stale consumer pin(s)")
