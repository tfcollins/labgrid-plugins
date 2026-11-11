"""Reusable workflow reporting retains diagnostics from failed hardware legs."""

from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("name", ["hw-request", "hw-matrix", "hw-matrix-v2", "infra-smoke"])
def test_workflow_uploads_provenance_and_diagnostics(name):
    data = yaml.safe_load(Path(f".github/workflows/{name}.yml").read_text())
    upload_steps = [
        step
        for job in data["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == "Upload to Prism"
    ]
    assert upload_steps
    for step in upload_steps:
        assert "always()" in step["if"]
        assert "--hardware-json" in step["run"]
        assert "--archive" in step["run"]
        assert "--pytest-log" in step["run"]
        assert "adi_lg_plugins.hw_ci.prism_upload.upload_run" in step["run"]
    assert "Prism upload stub" not in str(data)


@pytest.mark.parametrize("name", ["hw-request", "hw-matrix", "hw-matrix-v2"])
def test_workflow_records_passing_output_and_transcript(name):
    source = Path(f".github/workflows/{name}.yml").read_text()
    assert "junit_logging=all" in source
    assert "junit_log_passing_tests=true" in source
    assert "tee prism-pytest.log" in source
    assert "adi_lg_plugins.prism.run" in source
    assert "PRISM_CI_MATRIX" in source


def test_hardware_smoke_enables_reporting_from_repository_variable():
    data = yaml.safe_load(Path(".github/workflows/hardware-smoke.yml").read_text())
    job = data["jobs"]["smoke"]
    assert job["with"]["prism_upload"] == "${{ vars.PRISM_UPLOAD_ENABLED == 'true' }}"
    assert job["secrets"] == "inherit"


@pytest.mark.parametrize("name", ["hw-request", "hw-matrix", "hw-matrix-v2", "infra-smoke"])
def test_uploads_receive_github_token_for_job_lookup(name):
    data = yaml.safe_load(Path(f".github/workflows/{name}.yml").read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Upload to Prism":
                assert step["env"]["GITHUB_TOKEN"] == "${{ github.token }}"


@pytest.mark.parametrize("name", ["hw-request", "hw-matrix"])
def test_custom_upload_commands_receive_capture_artifact_environment(name):
    data = yaml.safe_load(Path(f".github/workflows/{name}.yml").read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == "Upload to Prism":
                script = step["run"]
                for variable, value in (
                    ("PRISM_ARCHIVE", ".prism-labgrid/artifacts.zip"),
                    ("PRISM_HARDWARE_JSON", ".prism-labgrid/hardware.json"),
                    ("PRISM_PYTEST_LOG", "prism-pytest.log"),
                ):
                    assert f"export {variable}={value}" in script
                    assert script.index(f"export {variable}") < script.index("if [ -n")
