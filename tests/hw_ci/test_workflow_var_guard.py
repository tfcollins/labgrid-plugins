from pathlib import Path

import yaml

WORKFLOWS = [
    ".github/workflows/hw-request.yml",
    ".github/workflows/noos-hw-request.yml",
    ".github/workflows/matlab-hw-request.yml",
]


def test_preflight_has_var_guard_first_step():
    for wf in WORKFLOWS:
        data = yaml.safe_load(Path(wf).read_text(encoding="utf-8"))
        preflight = data["jobs"]["preflight"]
        first = preflight["steps"][0]
        run = first.get("run", "")
        assert "inputs.coordinator" in run, f"{wf}: guard missing coordinator check"
        assert "inputs.runner-label" in run, f"{wf}: guard missing runner-label check"
        assert "::error::" in run, f"{wf}: guard not emitting ::error::"
