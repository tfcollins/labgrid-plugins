"""Answers saved by interactive commands, so a failed run can resume from them.

Each run is one JSON file under ``$XDG_CACHE_HOME/adi-lg/<command>/`` (default
``~/.cache``), rewritten after every answer so even an interrupted run keeps
what was typed. Files are readable by their owner only; callers must still
never save credentials for external services (API tokens, logins).

:func:`pick_run` offers the saved runs; :class:`Run` asks each question, or
takes its saved answer, and saves the answer.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from adi_lg_plugins.tools._choices import ask_choice

VERSION = 1
NEW = "new"


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

    def set(self, key: str, label: str, value: str | int | bool) -> None:
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


class Run:
    """One interactive run: each answer asked, or taken from a saved run, and saved.

    ``mode`` is "new", "resume" (saved answers are used as they are, and only
    what is missing is asked) or "review" (every question is asked again, with
    its saved answer as the default). ``command`` is the command line that
    resumes the run; ``directory`` is where it is saved (None: not saved).
    """

    def __init__(
        self,
        command: str,
        console: Console,
        directory: Path | None = None,
        saved: SavedAnswers | None = None,
        mode: str = NEW,
    ):
        self.command = command
        self.console = console
        self.directory = directory
        self.saved = saved or SavedAnswers()
        self.mode = mode

    def _saved(self, key: str, choices: Collection | None):
        answer = self.saved.answers.get(key)
        return answer if answer is not None and (choices is None or answer in choices) else None

    def will_ask(self, key: str) -> bool:
        return self.mode != "resume" or self._saved(key, None) is None

    def answer(
        self,
        key: str,
        label: str,
        ask: Callable,
        *,
        default=None,
        explain: str | None = None,
        choices: Collection | None = None,
        reask: bool = False,
    ):
        """``ask(default)`` unless resuming with ``key`` saved; the answer is saved.

        ``choices`` lists the answers still valid (e.g. templates that still
        exist); a saved answer outside them is asked again. ``reask`` asks even
        when resuming, with the saved answer as the default - for the answers
        most likely to have stopped a run (a URL, a login, an output path).
        Changing one of those voids nothing: its step is the one that failed.
        """
        saved = self._saved(key, choices)
        if saved is not None and self.mode == "resume" and not reask:
            return saved
        if saved is not None and (reask or self.mode == "review"):
            default = saved
        if explain:
            self.console.print(f"\n[dim]{escape(explain)}[/dim]")
        value = ask(default)
        # The steps a resumed run finished were done with its saved answers.
        if self.mode != NEW and not reask and value != self.saved.answers.get(key):
            self.saved.done.clear()
        self.saved.set(key, label, value)
        return value

    def given(self, key: str, label: str, value):
        """Save an answer taken from elsewhere (e.g. an inventory) instead of asked."""
        if self.mode != NEW and value != self.saved.answers.get(key):
            self.saved.done.clear()
        self.saved.set(key, label, value)
        return value

    def save_as(self, name: str) -> None:
        """Save under ``name`` from now on (e.g. the board name, once it is known)."""
        if self.directory is not None:
            self.saved.move_to(self.directory / f"{re.sub(r'[^A-Za-z0-9._-]', '_', name)}.json")

    def hint(self, how: str = "again") -> str:
        path = self.saved.path
        return (
            f"Answers saved to {path} - run `{self.command}` {how} and pick {path.stem} to resume."
        )

    @contextmanager
    def reporting(self) -> Iterator[None]:
        """End an error, Ctrl-C or EOF with where the answers are and how to resume."""
        try:
            yield
        except click.ClickException as e:
            if self.saved.path is not None and self.saved.path.exists():
                e.message += f"\n{self.hint()}"
            raise
        except (click.Abort, KeyboardInterrupt, EOFError):
            if self.saved.path is not None and self.saved.path.exists():
                click.echo(f"\n{self.hint()}")
            raise


def _shown(key: str, value) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if value == "":
        return "(default)"
    return "(hidden)" if "password" in key else str(value)


def pick_run(
    console: Console,
    *,
    command: str,
    directory: Path,
    headers: Sequence[str],
    describe: Callable[[SavedAnswers], Sequence[str]],
    new: str,
) -> Run:
    """Offer to resume a saved run, if there are any; otherwise start a new one.

    Saved runs are listed one per row: the run's name under ``headers[0]``,
    then ``describe(run)`` under the rest. ``new`` describes starting over.
    """
    runs = {run.path.stem: run for run in SavedAnswers.all_in(directory)}
    if not runs:
        return Run(command, console, directory)
    console.print("[bold]Saved answers from earlier runs[/bold]")
    pick = ask_choice(
        console,
        "Resume a saved run",
        [
            *((name, *describe(run)) for name, run in runs.items()),
            (NEW, *[""] * (len(headers) - 2), new),
        ],
        headers=headers,
        default=next(iter(runs)),
    )
    if pick == NEW:
        return Run(command, console, directory)
    saved = runs[pick]
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
    table.add_column("Question")
    table.add_column("Answer", overflow="fold")  # paths in full, not cut short
    for key, value in saved.answers.items():
        table.add_row(escape(saved.labels.get(key, key)), escape(_shown(key, value)))
    console.print(f"\n[bold]Saved answers for {escape(pick)}[/bold]")
    console.print(table)
    mode = ask_choice(
        console,
        "Use the saved answers",
        [
            ("resume", "as they are: ask only what is still unanswered"),
            ("review", "ask every question again, with the saved answer as its default"),
        ],
        default="resume",
    )
    return Run(command, console, directory, saved, mode)
