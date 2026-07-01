from pathlib import Path

import yaml

WORKFLOWS = [
    ".github/workflows/hw-request.yml",
    ".github/workflows/noos-hw-request.yml",
    ".github/workflows/matlab-hw-request.yml",
    ".github/workflows/infra-smoke.yml",
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


def test_infra_smoke_validate_gate_runs_on_hosted_runner():
    """infra-smoke gates on a hosted-runner ``validate`` job so a missing var or
    runner label fails fast with a clear ``::error::`` on ubuntu-latest, instead of
    an unschedulable self-hosted preflight job that just sits queued."""
    data = yaml.safe_load(Path(".github/workflows/infra-smoke.yml").read_text(encoding="utf-8"))
    validate = data["jobs"]["validate"]
    assert validate["runs-on"] == "ubuntu-latest", "validate must run on a hosted runner"
    run = validate["steps"][0]["run"]
    assert "inputs.coordinator" in run, "validate gate missing coordinator check"
    assert "inputs.runner-label" in run, "validate gate missing runner-label check"
    assert "inputs.preflight-runner-label" in run, (
        "validate gate missing preflight-runner-label check "
        "(the one that made preflight unschedulable)"
    )
    assert "::error::" in run, "validate gate not emitting ::error::"
    # preflight must depend on the gate so it only runs once validation passes.
    assert data["jobs"]["preflight"]["needs"] == "validate"
