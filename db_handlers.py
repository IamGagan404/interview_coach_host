"""
SQLite-backed session storage for the Interview Coach.

Drop-in replacement for the in-memory `sessions = {}` dict — same three
operations (create, read, update), but backed by a file on disk so state
survives uvicorn reloads and process restarts.

Usage in interview_main.py:

    from session_store import init_db, save_session, load_session, session_exists

    init_db()  # call once at startup

    # instead of: sessions[session_id] = state
    save_session(session_id, state)

    # instead of: state = sessions[session_id]
    state = load_session(session_id)

    # instead of: if session_id not in sessions
    if not session_exists(session_id):
        raise HTTPException(404, "session not found")
"""

import json
import sqlite3
from contextlib import contextmanager
from typing import Optional

DB_PATH = "sessions.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Call once at app startup (e.g. in a FastAPI startup event)."""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_session(session_id: str, state: dict) -> None:
    """Insert or update a session's state. state must be JSON-serializable
    (your InterviewState TypedDict is a plain dict, so this works as-is)."""
    state_json = json.dumps(state)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, state_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, state_json),
        )


def load_session(session_id: str) -> Optional[dict]:
    """Returns the state dict, or None if the session doesn't exist."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def session_exists(session_id: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row is not None


def delete_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))