from adi_lg_plugins.hw_ci import doctor
from adi_lg_plugins.hw_ci.doctor import CheckResult, FAIL, PASS, SKIP


def test_exit_code_and_table():
    results = [CheckResult("a", PASS), CheckResult("b", SKIP, "gh missing")]
    assert doctor.exit_code(results) == 0
    results.append(CheckResult("c", FAIL, "boom"))
    assert doctor.exit_code(results) == 1
    table = doctor.format_table(results)
    assert "a" in table and "PASS" in table and "FAIL" in table and "boom" in table


def test_skipped_banner():
    assert doctor.skipped_banner([CheckResult("a", PASS)]) is None
    banner = doctor.skipped_banner([CheckResult("a", SKIP), CheckResult("b", SKIP)])
    assert "2 check" in banner and "NOT verified" in banner


class _Match:
    def __init__(self, satisfiable, runner=None):
        self.satisfiable = satisfiable
        self.runner = runner


def test_check_discovery_uri_pass_with_fallback_runner(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    # board satisfiable but no per-leg runner -> resolves via fallback
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="hw-lab",
        probe=lambda part: _Match(True, runner=None),
    )
    assert res.status == PASS


def test_check_discovery_uri_fail_no_runner(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="",
        probe=lambda part: _Match(True, runner=None),
    )
    assert res.status == FAIL
    assert "runner" in res.detail


def test_check_discovery_empty_matrix_fails(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="hw-lab",
        probe=lambda part: _Match(False),
    )
    assert res.status == FAIL


def test_check_pin_flags_stale(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "hw.yml").write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.4\n",
        encoding="utf-8",
    )
    res = doctor.check_pin(repo_root=str(tmp_path))
    assert res.status == FAIL
    assert "v3.4" in res.detail


def test_run_doctor_no_coordinator_is_fail_not_crash(monkeypatch):
    import argparse
    monkeypatch.delenv("LG_COORDINATOR", raising=False)
    monkeypatch.delenv("ADI_LG_COORDINATOR", raising=False)
    ns = argparse.Namespace(mode="uri", coord=None, repo=None, test_root=None,
                            manifest=None, board_map=None, runner_label=None)
    rc = doctor.run_doctor(ns)   # must NOT raise
    assert rc == 1


def test_check_pin_skip_when_no_pins(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("uses: actions/checkout@v4\n", encoding="utf-8")
    assert doctor.check_pin(repo_root=str(tmp_path)).status == doctor.SKIP
