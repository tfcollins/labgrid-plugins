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
        '          "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"\n',
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
