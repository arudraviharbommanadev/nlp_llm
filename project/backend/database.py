import json
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "chat_history.sqlite3"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=MEMORY")
    connection.execute("PRAGMA synchronous=NORMAL")
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                transcript TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def save_session(messages: list[dict[str, str]]) -> dict[str, Any]:
    first_user_message = next(
        (message["content"] for message in messages if message["role"] == "user"),
        "New Chat Session",
    )
    title = first_user_message[:48].strip() or "New Chat Session"
    transcript = json.dumps(messages)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_sessions (title, transcript)
            VALUES (?, ?)
            """,
            (title, transcript),
        )
        connection.commit()

        session_id = cursor.lastrowid
        row = connection.execute(
            """
            SELECT id, title, created_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return dict(row)


def list_sessions() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at
            FROM chat_sessions
            ORDER BY id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_session(session_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, title, transcript, created_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    session = dict(row)
    session["messages"] = json.loads(session.pop("transcript"))
    return session
