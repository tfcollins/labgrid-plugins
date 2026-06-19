from adi_lg_plugins.hw_ci.cli import main


def test_init_uri_writes_files_and_guidance(tmp_path, capsys):
    rc = main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    assert rc == 0
    assert (tmp_path / ".github/workflows/hw-request.yml").is_file()
    assert (tmp_path / "test/hw/conftest.py").is_file()
    assert (tmp_path / "AGENTS.md").is_file()
    err = capsys.readouterr().err
    assert "gh variable set" in err and "doctor" in err


def test_init_refuses_existing_without_force(tmp_path):
    main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    assert main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"]) == 1


def test_init_force_overwrites(tmp_path):
    main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    rc = main(
        ["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw", "--force"]
    )
    assert rc == 0
