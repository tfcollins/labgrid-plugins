import subprocess
import sys
from pathlib import Path

from adi_lg_plugins.hw_ci.pin_lint import find_main_self_refs


def test_detects_main_action_ref(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        "      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main\n",
        encoding="utf-8",
    )
    assert find_main_self_refs([f]) == [(str(f), 1)]


def test_detects_main_git_install(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        '          "labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"\n',
        encoding="utf-8",
    )
    assert len(find_main_self_refs([f])) == 1


def test_clean_when_pinned(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        "      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@v3.5\n",
        encoding="utf-8",
    )
    assert find_main_self_refs([f]) == []


# --- the nox sessions themselves ----------------------------------------------
# `release_guard` and `lint_pins` are venv_backend="none" sessions: they run in
# nox's own Python, where nox is installed (pipx, uv tool, a system package) but
# this package and labgrid usually are not.

REPO = Path(__file__).resolve().parents[2]
_FAMILY = ("hw-request.yml", "noos-hw-request.yml", "matlab-hw-request.yml")
_RUN_SESSION = """
import importlib.util, sys, types

sys.modules["adi_lg_plugins"] = None  # not installed in nox's Python
nox = types.ModuleType("nox")
nox.session = lambda *a, **k: a[0] if a and callable(a[0]) else (lambda f: f)
nox.options = types.SimpleNamespace()
sys.modules["nox"] = nox

spec = importlib.util.spec_from_file_location("noxfile", sys.argv[1])
noxfile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(noxfile)


class Session:
    def log(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)
        sys.exit(3)


getattr(noxfile, sys.argv[2])(Session())
print("session passed")
"""


def _run_session(name, cwd):
    return subprocess.run(
        [sys.executable, "-I", "-c", _RUN_SESSION, str(REPO / "noxfile.py"), name],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _workflows(tmp_path, ref):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    for name in _FAMILY:
        text = (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8")
        (workflows / name).write_text(text.replace("@main", f"@{ref}"), encoding="utf-8")
    return tmp_path


def test_release_guard_session_passes_a_pinned_release_without_the_package(tmp_path):
    result = _run_session("release_guard", _workflows(tmp_path, "v9"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "session passed" in result.stdout


def test_release_guard_session_rejects_main_without_the_package():
    result = _run_session("release_guard", REPO)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "not release-ready" in result.stdout


def test_lint_pins_session_runs_without_the_package():
    result = _run_session("lint_pins", REPO)

    assert result.returncode == 0, result.stdout + result.stderr
