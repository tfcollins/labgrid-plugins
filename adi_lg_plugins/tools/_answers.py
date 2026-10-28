"""Answers saved by interactive commands, so a failed run can resume from them.

Each run is one JSON file under ``$XDG_CACHE_HOME/adi-lg/<command>/`` (default
``~/.cache``), rewritten after every answer so even an interrupted run keeps
what was typed. Files are readable by their owner only; callers must still
never save credentials for external services (API tokens, logins).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

VERSION = 1


def answers_dir(command: str) -> Path:
    """Where ``command`` keeps its saved runs."""
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "adi-lg" / command


class SavedAnswers:
    """One run's answers, the question each answered, and the steps it finished."""

    def __init__(
        self,
        path: Path | None = None,
        answers: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        done: list[str] | None = None,
        saved_at: str = "",
    ):
        self.path = path
        self.answers = dict(answers or {})
        self.labels = dict(labels or {})
        self.done = list(done or [])
        self.saved_at = saved_at

    @classmethod
    def load(cls, path: Path) -> SavedAnswers | None:
        """The run saved in ``path``, or None if it isn't one this version can read."""
        try:
            data = json.loads(path.read_text())
            if data["version"] != VERSION:
                return None
            return cls(
                path,
                data["answers"],
                data.get("labels"),
                data.get("done"),
                data.get("saved_at", ""),
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @classmethod
    def all_in(cls, directory: Path) -> list[SavedAnswers]:
        """Every readable run saved in ``directory``, most recent first."""
        runs = [run for path in directory.glob("*.json") if (run := cls.load(path))]
        return sorted(runs, key=lambda run: run.saved_at, reverse=True)

    def set(self, key: str, label: str, value: str) -> None:
        """Record the answer to ``label`` under ``key``."""
        self.answers[key] = value
        self.labels[key] = label
        self.save()

    def mark_done(self, step: str) -> None:
        if step not in self.done:
            self.done.append(step)
        self.save()

    def is_done(self, step: str) -> bool:
        return step in self.done

    def move_to(self, path: Path) -> None:
        """Save under ``path`` from now on (e.g. once the run has a name)."""
        old, self.path = self.path, path
        self.save()
        if old is not None and old != path:
            old.unlink(missing_ok=True)

    def delete(self) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)

    def save(self) -> None:
        """Write the file in one step, so a crash never leaves half of it."""
        if self.path is None:
            return
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.saved_at = time.strftime("%Y-%m-%d %H:%M")
        data = {
            "version": VERSION,
            "saved_at": self.saved_at,
            "answers": self.answers,
            "labels": self.labels,
            "done": self.done,
        }
        # mkstemp creates the file 0600; the name doesn't end in .json, so
        # all_in() never lists a temp file left by a crash.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.stem}-")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)
