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
    connection.execute("PRAGMA foreign_keys=ON")
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
                transcript TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_session_columns(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model_used TEXT,
                task_type TEXT,
                orchestrator_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                message_index INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orchestrator_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                query_type TEXT,
                primary_intent TEXT,
                secondary_intents_json TEXT NOT NULL DEFAULT '[]',
                needs_rag INTEGER NOT NULL DEFAULT 0,
                rag_mode TEXT NOT NULL DEFAULT 'none',
                response_strategy TEXT,
                final_aggregation_model TEXT,
                tasks_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            )
            """
        )
        connection.commit()


def _ensure_session_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(chat_sessions)").fetchall()
    }
    required_columns = {
        "updated_at": "TEXT",
        "session_type": "TEXT NOT NULL DEFAULT 'study'",
        "pinned": "INTEGER NOT NULL DEFAULT 0",
        "last_model_used": "TEXT",
        "primary_intent": "TEXT",
        "needs_rag": "INTEGER NOT NULL DEFAULT 0",
    }
    for column_name, definition in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE chat_sessions ADD COLUMN {column_name} {definition}")

    connection.execute(
        """
        UPDATE chat_sessions
        SET updated_at = COALESCE(updated_at, created_at)
        WHERE updated_at IS NULL
        """
    )


def save_session(
    messages: list[dict[str, Any]],
    orchestrator_runs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    first_user_message = next(
        (message["content"] for message in messages if message["role"] == "user"),
        "New Chat Session",
    )
    title = first_user_message[:48].strip() or "New Chat Session"
    transcript = json.dumps(
        [
            {
                "role": message["role"],
                "content": message["content"],
            }
            for message in messages
        ]
    )
    last_model_used = next(
        (message.get("model_used") for message in reversed(messages) if message.get("model_used")),
        None,
    )
    primary_intent = next(
        (
            message.get("orchestrator", {}).get("primary_intent")
            for message in reversed(messages)
            if message.get("orchestrator")
        ),
        None,
    )
    needs_rag = int(
        any(message.get("orchestrator", {}).get("needs_rag") for message in messages)
    )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_sessions (
                title,
                transcript,
                updated_at,
                session_type,
                pinned,
                last_model_used,
                primary_intent,
                needs_rag
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, 'study', 0, ?, ?, ?)
            """,
            (title, transcript, last_model_used, primary_intent, needs_rag),
        )
        session_id = cursor.lastrowid

        for index, message in enumerate(messages):
            connection.execute(
                """
                INSERT INTO chat_messages (
                    session_id,
                    role,
                    content,
                    model_used,
                    task_type,
                    orchestrator_json,
                    message_index
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    message["role"],
                    message["content"],
                    message.get("model_used"),
                    message.get("task_type"),
                    json.dumps(message.get("orchestrator")) if message.get("orchestrator") else None,
                    index,
                ),
            )

        for run in orchestrator_runs or _extract_orchestrator_runs(messages):
            connection.execute(
                """
                INSERT INTO orchestrator_runs (
                    session_id,
                    query_type,
                    primary_intent,
                    secondary_intents_json,
                    needs_rag,
                    rag_mode,
                    response_strategy,
                    final_aggregation_model,
                    tasks_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    run.get("query_type"),
                    run.get("primary_intent"),
                    json.dumps(run.get("secondary_intents", [])),
                    int(run.get("needs_rag", False)),
                    run.get("rag_mode", "none"),
                    run.get("response_strategy"),
                    run.get("final_aggregation_model"),
                    json.dumps(run.get("tasks", [])),
                ),
            )

        connection.commit()

        row = connection.execute(
            """
            SELECT
                id,
                title,
                created_at,
                updated_at,
                pinned,
                last_model_used,
                primary_intent,
                needs_rag
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return dict(row)


def _extract_orchestrator_runs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for message in messages:
        orchestrator = message.get("orchestrator")
        if orchestrator and orchestrator not in runs:
            runs.append(orchestrator)
    return runs


def list_sessions() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                title,
                created_at,
                updated_at,
                pinned,
                last_model_used,
                primary_intent,
                needs_rag
            FROM chat_sessions
            ORDER BY pinned DESC, id DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def get_session(session_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                id,
                title,
                transcript,
                created_at,
                updated_at,
                pinned,
                last_model_used,
                primary_intent,
                needs_rag
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

        if row is None:
            return None

        message_rows = connection.execute(
            """
            SELECT role, content, model_used, task_type, orchestrator_json
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY message_index ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        run_rows = connection.execute(
            """
            SELECT
                query_type,
                primary_intent,
                secondary_intents_json,
                needs_rag,
                rag_mode,
                response_strategy,
                final_aggregation_model,
                tasks_json,
                created_at
            FROM orchestrator_runs
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    session = dict(row)
    if message_rows:
        session["messages"] = [
            {
                "role": message["role"],
                "content": message["content"],
                "model_used": message["model_used"],
                "task_type": message["task_type"],
                "orchestrator": json.loads(message["orchestrator_json"])
                if message["orchestrator_json"]
                else None,
            }
            for message in message_rows
        ]
    else:
        session["messages"] = json.loads(session.pop("transcript"))
        return session

    session["orchestrator_runs"] = [
        {
            "query_type": run["query_type"],
            "primary_intent": run["primary_intent"],
            "secondary_intents": json.loads(run["secondary_intents_json"]),
            "needs_rag": bool(run["needs_rag"]),
            "rag_mode": run["rag_mode"],
            "response_strategy": run["response_strategy"],
            "final_aggregation_model": run["final_aggregation_model"],
            "tasks": json.loads(run["tasks_json"]),
            "created_at": run["created_at"],
        }
        for run in run_rows
    ]
    session.pop("transcript", None)
    return session


def delete_session(session_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM chat_sessions WHERE id = ?",
            (session_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
