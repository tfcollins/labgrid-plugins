"""One-time admin bootstrap token."""

import secrets


def generate_bootstrap_token() -> str:
    return secrets.token_urlsafe(24)
