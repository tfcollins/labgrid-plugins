"""Unit tests for the numbered option lists shown by interactive prompts."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console
from rich.prompt import Prompt

from adi_lg_plugins.tools._choices import ask_choice


def _answers(monkeypatch, *answers):
    """Stub Prompt.ask with successive answers; return the recorded calls."""
    calls = []
    pending = list(answers)

    def _ask(prompt, *args, **kwargs):
        calls.append((prompt, kwargs))
        return pending.pop(0)

    monkeypatch.setattr(Prompt, "ask", staticmethod(_ask))
    return calls


def _console():
    return Console(file=StringIO(), width=100)


@pytest.mark.parametrize(("answer", "expected"), [("2", "beta"), ("beta", "beta")])
def test_answer_by_number_or_name(monkeypatch, answer, expected):
    _answers(monkeypatch, answer)

    assert ask_choice(_console(), "Pick", ["alpha", "beta", "gamma"]) == expected


def test_choices_are_listed_one_per_line_not_inline_in_the_prompt(monkeypatch):
    calls = _answers(monkeypatch, "alpha")
    console = _console()

    ask_choice(console, "Pick", ["alpha", "beta", "gamma"], default="alpha")

    lines = console.file.getvalue().splitlines()
    for number, name in enumerate(["alpha", "beta", "gamma"], 1):
        assert sum(name in line for line in lines) == 1
        assert any(str(number) in line and name in line for line in lines)
    prompt, kwargs = calls[0]
    assert kwargs["show_choices"] is False
    assert kwargs["default"] == "alpha"


def test_descriptions_share_the_option_row(monkeypatch):
    _answers(monkeypatch, "apc")
    console = _console()

    ask_choice(
        console,
        "Power type",
        [("apc", "APC PDU (SNMP)"), ("vesync", "VeSync smart plug")],
        headers=("Type", "Description"),
    )

    lines = console.file.getvalue().splitlines()
    assert any("apc" in line and "APC PDU (SNMP)" in line for line in lines)
    assert any("vesync" in line and "VeSync smart plug" in line for line in lines)
    assert any("Type" in line and "Description" in line for line in lines)


def test_long_lists_wrap_into_columns(monkeypatch):
    _answers(monkeypatch, "m00")
    console = _console()
    names = [f"m{i:02}" for i in range(30)]

    ask_choice(console, "Model", names)

    assert len(console.file.getvalue().splitlines()) < len(names)


def test_invalid_answers_are_asked_again(monkeypatch):
    calls = _answers(monkeypatch, "", "4", "delta", "gamma")

    assert ask_choice(_console(), "Pick", ["alpha", "beta", "gamma"]) == "gamma"
    assert len(calls) == 4


def test_a_note_follows_the_options_before_the_prompt(monkeypatch):
    console = _console()

    def _ask(prompt, *args, **kwargs):
        console.print("PROMPT")
        return "alpha"

    monkeypatch.setattr(Prompt, "ask", staticmethod(_ask))

    ask_choice(console, "Pick", ["alpha", "beta"], note="beta is slow")

    lines = console.file.getvalue().splitlines()
    assert lines.index("beta is slow") == lines.index("PROMPT") - 1
    assert any("beta" in line for line in lines[: lines.index("beta is slow")])
