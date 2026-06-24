"""Shared helpers for the Tick deploy drivers."""


def stdout_text(result):
    """Join a labgrid ``run_check`` stdout result (list[str]) into one string."""
    if isinstance(result, (list, tuple)):
        return "\n".join(str(x) for x in result)
    return str(result)
