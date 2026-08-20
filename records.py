"""
records.py
----------
Persists the outcome of each corresponding-author check: either a
confirmed ORCID (from "This is me") or a manually-entered ORCID flagged
for production review (from "Not me").

Uses SQLite (a single file, no separate database service to run) --
appropriate for this prototype's scale. On Render's free tier the disk
is ephemeral and resets on redeploy; for anything beyond a demo, point
DB_PATH at a persistent disk (Render offers this on paid plans) or swap
this module for a hosted database.
"""

import os
import re
import sqlite3
import time
from contextlib import contextmanager
from typing import Optional

DB_PATH = os.environ.get("RECORDS_DB_PATH", os.path.join(os.path.dirname(__file__), "records.db"))

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


class InvalidOrcidError(ValueError):
    pass


def _init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS author_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT,
                author_name TEXT NOT NULL,
                orcid TEXT NOT NULL,
                status TEXT NOT NULL,              -- 'confirmed' | 'flagged'
                source TEXT,                       -- e.g. 'CrossRef', 'ORCID registry', 'manual'
                note TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS author_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id TEXT NOT NULL,
                author_name TEXT NOT NULL,
                role TEXT NOT NULL,                -- 'corresponding' | 'co-author' | 'other'
                body TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def validate_orcid_format(orcid: str) -> str:
    """Checks the standard XXXX-XXXX-XXXX-XXXX shape (last char may be X,
    the ISO 7064 checksum character). Raises InvalidOrcidError if malformed."""
    cleaned = orcid.strip().upper()
    cleaned = cleaned.replace("HTTPS://ORCID.ORG/", "").replace("ORCID.ORG/", "")
    if not ORCID_PATTERN.match(cleaned):
        raise InvalidOrcidError(
            f"'{orcid}' doesn't look like a valid ORCID iD. Expected format: 0000-0001-5250-9122"
        )
    return cleaned


def record_confirmation(article_id: str, author_name: str, orcid: str, source: str) -> dict:
    orcid = validate_orcid_format(orcid)
    row = {
        "article_id": article_id or "",
        "author_name": author_name,
        "orcid": orcid,
        "status": "confirmed",
        "source": source or "unspecified",
        "note": None,
        "created_at": time.time(),
    }
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO author_records (article_id, author_name, orcid, status, source, note, created_at) "
            "VALUES (:article_id, :author_name, :orcid, :status, :source, :note, :created_at)",
            row,
        )
        conn.commit()
        row["id"] = cur.lastrowid
    return row


def record_flag(article_id: str, author_name: str, orcid: str, note: Optional[str] = None) -> dict:
    orcid = validate_orcid_format(orcid)
    row = {
        "article_id": article_id or "",
        "author_name": author_name,
        "orcid": orcid,
        "status": "flagged",
        "source": "manual",
        "note": note or "Reviewer indicated the suggested match was not correct; ORCID entered manually.",
        "created_at": time.time(),
    }
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO author_records (article_id, author_name, orcid, status, source, note, created_at) "
            "VALUES (:article_id, :author_name, :orcid, :status, :source, :note, :created_at)",
            row,
        )
        conn.commit()
        row["id"] = cur.lastrowid
    return row


def list_records(article_id: Optional[str] = None) -> list:
    with _connect() as conn:
        if article_id:
            cur = conn.execute(
                "SELECT * FROM author_records WHERE article_id = ? ORDER BY created_at DESC", (article_id,)
            )
        else:
            cur = conn.execute("SELECT * FROM author_records ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]


VALID_ROLES = {"corresponding", "co-author", "other"}


def add_comment(article_id: str, author_name: str, role: str, body: str) -> dict:
    role = (role or "other").strip().lower()
    if role not in VALID_ROLES:
        role = "other"
    body = (body or "").strip()
    if not body:
        raise ValueError("Comment can't be empty.")
    if not article_id:
        raise ValueError("A comment needs an article to attach to.")

    row = {
        "article_id": article_id,
        "author_name": author_name,
        "role": role,
        "body": body,
        "created_at": time.time(),
    }
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO author_comments (article_id, author_name, role, body, created_at) "
            "VALUES (:article_id, :author_name, :role, :body, :created_at)",
            row,
        )
        conn.commit()
        row["id"] = cur.lastrowid
    return row


def list_comments(article_id: str, author_name: str) -> list:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM author_comments WHERE article_id = ? AND author_name = ? ORDER BY created_at ASC",
            (article_id, author_name),
        )
        return [dict(r) for r in cur.fetchall()]


def reset_all() -> None:
    """Wipes every confirmation, flag, and comment. Used by the demo
    'Reset' control -- not gated by anything beyond the UI's confirm step,
    since this app has no auth/user model. Don't expose this endpoint
    publicly for a real deployment without adding access control."""
    with _connect() as conn:
        conn.execute("DELETE FROM author_records")
        conn.execute("DELETE FROM author_comments")
        conn.commit()


_init_db()
