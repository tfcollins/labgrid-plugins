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


# Workflows whose legs boot a board via `adi-lg request` and must power it off
# afterwards by default (boards shouldn't stay powered 24/7 after CI runs).
POWER_DOWN_WORKFLOWS = [
    ".github/workflows/hw-request.yml",
    ".github/workflows/matlab-hw-request.yml",
    ".github/workflows/infra-smoke.yml",
]


def test_workflows_declare_power_down_default_true():
    """Each board-booting workflow exposes a `power-down` input defaulting to true
    and actually threads `--power-down` into its `adi-lg request` leg."""
    for wf in POWER_DOWN_WORKFLOWS:
        text = Path(wf).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
        # YAML parses the `on:` trigger key as boolean True.
        inputs = data[True]["workflow_call"]["inputs"]
        pd = inputs.get("power-down")
        assert pd is not None, f"{wf}: missing power-down input"
        assert pd["type"] == "boolean", f"{wf}: power-down must be boolean"
        assert pd["default"] is True, f"{wf}: power-down must default to true"
        assert "--power-down" in text, f"{wf}: leg does not pass --power-down"
