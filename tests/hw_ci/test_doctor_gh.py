from adi_lg_plugins.hw_ci import doctor
from adi_lg_plugins.hw_ci.doctor import FAIL, PASS, SKIP


def test_repo_vars_skip_when_gh_absent():
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (127, ""))
    assert res.status == SKIP


def test_repo_vars_pass_when_all_present():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\nHW_PREFLIGHT_RUNNER\n"
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (0, out))
    assert res.status == PASS


def test_repo_vars_fail_when_missing():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\n"  # missing HW_PREFLIGHT_RUNNER
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (0, out))
    assert res.status == FAIL
    assert "HW_PREFLIGHT_RUNNER" in res.detail


def test_matlab_requires_matlab_bin():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\nHW_PREFLIGHT_RUNNER\n"
    res = doctor.check_repo_vars("o/r", "matlab", gh=lambda args: (0, out))
    assert res.status == FAIL and "MATLAB_BIN" in res.detail


def test_runner_scope_pass():
    out = '{"runners":[{"labels":[{"name":"hw-lab"}]}]}'
    res = doctor.check_runner_scope("o/r", ["hw-lab"], gh=lambda args: (0, out))
    assert res.status == PASS


def test_runner_scope_fail_missing_label():
    out = '{"runners":[{"labels":[{"name":"other"}]}]}'
    res = doctor.check_runner_scope("o/r", ["hw-lab"], gh=lambda args: (0, out))
    assert res.status == FAIL


def test_runner_scope_skip_when_no_labels():
    res = doctor.check_runner_scope("o/r", [], gh=lambda args: (0, "{}"))
    assert res.status == SKIP


def test_runner_scope_skip_when_gh_absent():
    res = doctor.check_runner_scope("o/r", ["hw-lab"], gh=lambda args: (127, ""))
    assert res.status == SKIP
