"""SQLite-backed user and session storage."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

import aiosqlite

from .passwords import hash_password


@dataclass
class User:
    id: int
    username: str
    password_hash: str | None
    role: str
    oidc_subject: str | None
    created_at: float
    disabled_at: float | None


def _row_to_user(row) -> User:
    return User(
        id=row[0],
        username=row[1],
        password_hash=row[2],
        role=row[3],
        oidc_subject=row[4],
        created_at=row[5],
        disabled_at=row[6],
    )


_USER_COLS = "id, username, password_hash, role, oidc_subject, created_at, disabled_at"


class AuthStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def create_user(
        self,
        *,
        username: str,
        password: str | None,
        role: str,
        oidc_subject: str | None = None,
    ) -> User:
        if role not in ("admin", "user"):
            raise ValueError(f"invalid role: {role}")
        ph = hash_password(password) if password else None
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            try:
                cur = await conn.execute(
                    "INSERT INTO users (username, password_hash, role, oidc_subject, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (username, ph, role, oidc_subject, now),
                )
                await conn.commit()
                uid = cur.lastrowid
            except aiosqlite.IntegrityError as e:
                raise ValueError(f"username or oidc_subject already exists: {e}") from e
            cur = await conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (uid,))
            row = await cur.fetchone()
        return _row_to_user(row)

    async def get_user_by_id(self, user_id: int) -> User | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,))
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def get_user_by_username(self, username: str) -> User | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_USER_COLS} FROM users WHERE username = ?", (username,)
            )
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def get_user_by_oidc_subject(self, subject: str) -> User | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_USER_COLS} FROM users WHERE oidc_subject = ?", (subject,)
            )
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def list_users(self) -> list[User]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(f"SELECT {_USER_COLS} FROM users ORDER BY username")
            rows = await cur.fetchall()
        return [_row_to_user(r) for r in rows]

    async def user_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM users")
            (n,) = await cur.fetchone()
        return int(n)

    async def delete_user(self, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            await conn.commit()

    async def set_password(self, user_id: int, password: str) -> None:
        ph = hash_password(password)
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (ph, user_id))
            await conn.commit()

    async def set_role(self, user_id: int, role: str) -> None:
        if role not in ("admin", "user"):
            raise ValueError(f"invalid role: {role}")
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            await conn.commit()

    async def set_disabled(self, user_id: int, disabled: bool) -> None:
        ts = time.time() if disabled else None
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("UPDATE users SET disabled_at = ? WHERE id = ?", (ts, user_id))
            await conn.commit()

    async def create_session(self, user_id: int, *, ttl_seconds: int) -> str:
        sid = secrets.token_urlsafe(32)
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT INTO sessions (id, user_id, created_at, expires_at, last_seen_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (sid, user_id, now, now + ttl_seconds, now),
            )
            await conn.commit()
        return sid

    async def resolve_session(self, session_id: str) -> User | None:
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT u.{', u.'.join(_USER_COLS.split(', '))} "
                "FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.id = ? AND s.expires_at > ? AND u.disabled_at IS NULL",
                (session_id, now),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            await conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE id = ?", (now, session_id)
            )
            await conn.commit()
        return _row_to_user(row)

    async def delete_session(self, session_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await conn.commit()

    async def purge_expired_sessions(self) -> int:
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            await conn.commit()
        return cur.rowcount
