import importlib.util
from pathlib import Path

import nox

# Define default sessions
## `typecheck` is opt-in (`nox -s typecheck`) until the baseline is cleaned;
## running `nox` with no args should not fail on pre-existing diagnostics.
nox.options.sessions = ["lint", "tests", "docs"]
nox.options.default_venv_backend = "uv"


@nox.session
def tests(session):
    """Run tests."""
    # Install the root package and the coordinator API package in editable
    # mode with their dev dependencies so the full repo test suite can import
    # both trees during collection.
    session.install("-e", ".[dev]", "-e", "coordinator/api[dev]")
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


def _hw_ci_module(name):
    """Load ``adi_lg_plugins/hw_ci/<name>.py`` by path, not as a package import.

    The sessions below run without a venv, in nox's own Python, where this
    package - and labgrid, which its ``__init__`` imports - usually isn't
    installed. These modules use the standard library only.
    """
    path = Path(__file__).parent / "adi_lg_plugins" / "hw_ci" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_noxfile_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@nox.session(venv_backend="none")
def lint_pins(session):
    """Fail if any consumer-facing example pins != RECOMMENDED_PIN (or uses @main)."""
    pin = _hw_ci_module("_release").RECOMMENDED_PIN
    pin_lint = _hw_ci_module("pin_lint")

    violations = pin_lint.find_consumer_pin_violations(pin_lint.CONSUMER_PIN_PATHS, pin)
    for f, line, found in violations:
        session.log(f"{f}:{line}: consumer pin @{found} != @{pin}")
    if violations:
        session.error(f"{len(violations)} stale consumer pin(s)")


@nox.session(venv_backend="none")
def release_guard(session):
    """RELEASE-ONLY. Fail if any hw-request-family workflow still has an @main
    self-ref (i.e. scripts/pin-release-refs.sh was not run). MUST NOT run on
    main — main keeps @main by design."""
    find_main_self_refs = _hw_ci_module("pin_lint").find_main_self_refs

    family = [
        ".github/workflows/hw-request.yml",
        ".github/workflows/noos-hw-request.yml",
        ".github/workflows/matlab-hw-request.yml",
    ]
    refs = find_main_self_refs(family)
    for f, line in refs:
        session.log(f"{f}:{line}: internal @main self-ref — run scripts/pin-release-refs.sh")
    if refs:
        session.error(f"{len(refs)} unpinned @main self-ref(s) — not release-ready")
