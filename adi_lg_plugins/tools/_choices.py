"""Numbered option lists for interactive prompts.

rich's ``Prompt.ask(choices=...)`` runs every option together inside the prompt
(``[a/b/.../z]``); these show one option per row instead and accept either the
row number or the option itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

# Plain lists longer than this are laid out in columns rather than one per line.
_MAX_ROWS = 12


def ask_choice(
    console: Console,
    prompt: str,
    options: Sequence[str | tuple[str, ...]],
    *,
    headers: Sequence[str] = (),
    default: str | None = None,
    note: str | None = None,
) -> str:
    """List ``options`` numbered, then ask for one by number or name.

    An option is a name, or a tuple of the name and its description column(s),
    titled by ``headers`` (the first header names the option column). ``note``
    is printed under the options.
    """
    rows = [(o,) if isinstance(o, str) else tuple(o) for o in options]
    names = [r[0] for r in rows]
    console.print(_render(rows, headers, default))
    if note:
        console.print(note)
    by_number = {str(i): name for i, name in enumerate(names, 1)}
    while True:
        answer = (
            Prompt.ask(prompt, choices=names + list(by_number), show_choices=False, default=default)
            or ""
        ).strip()
        if answer in names:
            return answer
        if answer in by_number:
            return by_number[answer]
        console.print("    [red]enter a number or a name from the list[/red]")


def _render(rows: list[tuple[str, ...]], headers: Sequence[str], default: str | None):
    if headers or any(len(r) > 1 for r in rows):
        table = Table(
            box=box.SIMPLE_HEAD, show_header=bool(headers), show_edge=False, pad_edge=False
        )
        table.add_column("#", justify="right", style="dim")
        for header in headers or [""] * len(rows[0]):
            table.add_column(header)
        for i, row in enumerate(rows, 1):
            table.add_row(str(i), *row, style="bold" if row[0] == default else None)
        return table
    items = [f"[dim]{i:>2})[/dim] {r[0]}" for i, r in enumerate(rows, 1)]
    if len(items) <= _MAX_ROWS:
        return "\n".join(items)
    return Columns(items, column_first=True, padding=(0, 3))
