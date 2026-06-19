from adi_lg_plugins.hw_ci.pin_lint import find_consumer_pin_violations


def test_flags_stale_and_main(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.4\n"
        "uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@main\n",
        encoding="utf-8",
    )
    viol = find_consumer_pin_violations([f], "v3.5")
    assert len(viol) == 2
    founds = {v[2] for v in viol}
    assert founds == {"v3.4", "main"}


def test_clean_when_matches(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.5\n",
        encoding="utf-8",
    )
    assert find_consumer_pin_violations([f], "v3.5") == []


def test_ignores_other_refs(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text("uses: actions/checkout@v4\n", encoding="utf-8")
    assert find_consumer_pin_violations([f], "v3.5") == []
