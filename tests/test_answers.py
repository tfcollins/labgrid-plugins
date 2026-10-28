"""Unit tests for the saved answers interactive commands resume from."""

from __future__ import annotations

import json
import stat

from adi_lg_plugins.tools._answers import VERSION, SavedAnswers, answers_dir


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_answers_dir_follows_xdg_cache_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert answers_dir("netbox-add-hardware") == tmp_path / "adi-lg" / "netbox-add-hardware"

    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert answers_dir("x") == tmp_path / "home" / ".cache" / "adi-lg" / "x"


def test_each_answer_is_saved_at_once_readable_only_by_the_owner(tmp_path):
    path = tmp_path / "runs" / "b1.json"
    saved = SavedAnswers(path)

    saved.set("name", "Board name", "b1")

    assert SavedAnswers.load(path).answers == {"name": "b1"}
    assert SavedAnswers.load(path).labels == {"name": "Board name"}
    assert _mode(path) == 0o600
    assert _mode(path.parent) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["b1.json"]  # no temp file left behind


def test_nothing_is_written_until_the_run_has_a_file(tmp_path):
    saved = SavedAnswers()
    saved.set("template", "Board template", "soc-ssh")

    saved.move_to(tmp_path / "b1.json")

    assert SavedAnswers.load(tmp_path / "b1.json").answers == {"template": "soc-ssh"}


def test_moving_to_a_new_name_removes_the_old_file(tmp_path):
    saved = SavedAnswers(tmp_path / "b1.json")
    saved.set("name", "Board name", "b1")

    saved.move_to(tmp_path / "b2.json")

    assert not (tmp_path / "b1.json").exists()
    assert (tmp_path / "b2.json").exists()


def test_finished_steps_are_saved(tmp_path):
    saved = SavedAnswers(tmp_path / "b1.json")
    saved.set("site", "NetBox site slug", "lab3")
    saved.mark_done("plan")
    saved.mark_done("netbox")
    saved.mark_done("netbox")

    loaded = SavedAnswers.load(tmp_path / "b1.json")
    assert loaded.done == ["plan", "netbox"]
    assert loaded.is_done("netbox") and not loaded.is_done("exporter")


def test_unreadable_files_are_skipped(tmp_path):
    good = SavedAnswers(tmp_path / "good.json")
    good.set("name", "Board name", "good")
    (tmp_path / "corrupt.json").write_text("{not json")
    (tmp_path / "list.json").write_text("[]")
    (tmp_path / "future.json").write_text(json.dumps({"version": VERSION + 1, "answers": {}}))

    assert [r.path.name for r in SavedAnswers.all_in(tmp_path)] == ["good.json"]
    assert SavedAnswers.all_in(tmp_path / "missing") == []


def test_runs_are_listed_most_recent_first(tmp_path):
    for name, saved_at in (("old", "2026-01-01 09:00"), ("new", "2026-10-28 09:00")):
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"version": VERSION, "saved_at": saved_at, "answers": {"name": name}})
        )

    assert [r.answers["name"] for r in SavedAnswers.all_in(tmp_path)] == ["new", "old"]


def test_delete_removes_the_file(tmp_path):
    saved = SavedAnswers(tmp_path / "b1.json")
    saved.set("name", "Board name", "b1")

    saved.delete()

    assert not (tmp_path / "b1.json").exists()


def test_an_answer_given_instead_of_asked_is_saved_and_voids_steps_it_changes(tmp_path):
    from rich.console import Console

    from adi_lg_plugins.tools._answers import Run

    saved = SavedAnswers(tmp_path / "b1.json", {"power": "apc"}, done=["netbox"])
    run = Run("cmd", Console(), tmp_path, saved, mode="resume")

    assert run.given("power", "Power type", "apc") == "apc"
    assert saved.done == ["netbox"]

    run.given("power", "Power type", "cyberpower")
    assert SavedAnswers.load(tmp_path / "b1.json").answers == {"power": "cyberpower"}
    assert saved.labels["power"] == "Power type"
    assert saved.done == []
