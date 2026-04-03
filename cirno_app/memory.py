from __future__ import annotations

import math
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class FactItem:
    session_id: str
    key: str
    value: str
    confidence: float
    id: int | None = None
    status: str = "active"
    decay_score: float = 1.0


@dataclass
class SessionItem:
    session_id: str
    created_at: str
    message_count: int


class MemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._memory_mode = str(db_path) == ":memory:"
        self._shared_conn: sqlite3.Connection | None = None
        if not self._memory_mode:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if self._memory_mode:
            if self._shared_conn is None:
                self._shared_conn = sqlite3.connect(":memory:", timeout=30)
                self._shared_conn.row_factory = sqlite3.Row
                self._shared_conn.execute("PRAGMA foreign_keys = ON")
                self._shared_conn.execute("PRAGMA busy_timeout = 30000")
            return self._shared_conn

        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _ensure_column(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_def: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    def _init_db(self) -> None:
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(2):
            try:
                with self._conn() as conn:
                    try:
                        conn.execute("PRAGMA journal_mode = WAL")
                    except sqlite3.OperationalError:
                        # Some restricted Windows directories reject WAL; fall back to default journal mode.
                        pass
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS sessions (
                            session_id TEXT PRIMARY KEY,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                            role TEXT NOT NULL,
                            content TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            CHECK(role IN ('user', 'assistant'))
                        )
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS facts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                            canonical_key TEXT NOT NULL,
                            value TEXT NOT NULL,
                            normalized_value TEXT NOT NULL,
                            confidence REAL NOT NULL,
                            status TEXT NOT NULL DEFAULT 'active',
                            source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
                            superseded_by INTEGER,
                            valid_from TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            valid_to TEXT,
                            decay_score REAL NOT NULL DEFAULT 1.0,
                            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            CHECK(status IN ('active', 'superseded', 'expired', 'deleted')),
                            CHECK(confidence >= 0.0 AND confidence <= 1.0),
                            CHECK(decay_score >= 0.0 AND decay_score <= 1.0)
                        )
                        """
                    )
                    self._ensure_column(conn, "facts", "session_id", "TEXT")
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id)"
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_facts_session_key_status ON facts(session_id, canonical_key, status)"
                    )
                    conn.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_one_active_per_key
                        ON facts(session_id, canonical_key)
                        WHERE status = 'active' AND session_id IS NOT NULL
                        """
                    )
                    conn.execute(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_facts_one_active_per_value
                        ON facts(session_id, canonical_key, normalized_value)
                        WHERE status = 'active' AND session_id IS NOT NULL
                        """
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS summaries (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                            summary TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_summaries_session_id_id ON summaries(session_id, id)"
                    )
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS fact_actions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            action_type TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                return
            except sqlite3.OperationalError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.2)
                    continue
                raise
        if last_error is not None:
            raise last_error

    def get_latest_session_id(self) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT s.session_id
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.session_id
                GROUP BY s.session_id, s.created_at
                ORDER BY COALESCE(MAX(m.id), 0) DESC, s.created_at DESC
                LIMIT 1
                """
            ).fetchone()
        return row["session_id"] if row else None

    def create_session(self, session_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id) VALUES (?)",
                (session_id,),
            )

    def list_sessions(self, limit: int = 20) -> list[SessionItem]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT s.session_id, s.created_at, COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN messages m ON m.session_id = s.session_id
                GROUP BY s.session_id, s.created_at
                ORDER BY COALESCE(MAX(m.id), 0) DESC, s.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SessionItem(
                session_id=row["session_id"],
                created_at=row["created_at"],
                message_count=row["message_count"],
            )
            for row in rows
        ]

    def ensure_session(self, session_id: str) -> None:
        self.create_session(session_id)

    def save_message(self, session_id: str, role: str, content: str) -> int:
        self.ensure_session(session_id)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            return int(cur.lastrowid)

    def delete_message(self, message_id: int) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
            return cur.rowcount > 0

    def get_recent_messages(self, session_id: str, turns: int) -> list[dict[str, str]]:
        limit = max(turns * 2, 2)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        messages = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

        # When truncating a long session, keep only complete user/assistant turns.
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
        while messages and messages[-1]["role"] != "assistant":
            messages.pop()
        normalized: list[dict[str, str]] = []
        expected_role = "user"
        for item in messages:
            if item["role"] != expected_role:
                continue
            normalized.append(item)
            expected_role = "assistant" if expected_role == "user" else "user"

        if normalized and normalized[-1]["role"] == "assistant":
            return normalized
        return []

    def save_summary(self, session_id: str, summary: str) -> None:
        self.ensure_session(session_id)
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO summaries (session_id, summary) VALUES (?, ?)",
                (session_id, summary),
            )

    def get_latest_summary(self, session_id: str) -> str:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT summary
                FROM summaries
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return row["summary"] if row else ""

    def _normalize_key(self, key: str) -> str:
        return " ".join(key.strip().lower().split())

    def _normalize_value(self, value: str) -> str:
        return " ".join(value.strip().lower().split())

    def _touch_fact(self, conn: sqlite3.Connection, fact_id: int, confidence: float) -> None:
        conn.execute(
            """
            UPDATE facts
            SET confidence = MAX(confidence, ?),
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                decay_score = MIN(decay_score + 0.05, 1.0)
            WHERE id = ?
            """,
            (confidence, fact_id),
        )

    def _record_action(self, conn: sqlite3.Connection, action_type: str, payload: dict) -> None:
        # Persist manual governance actions so CLI can undo reliably.
        conn.execute(
            "INSERT INTO fact_actions (action_type, payload_json) VALUES (?, ?)",
            (action_type, json.dumps(payload, ensure_ascii=False)),
        )

    def _snapshot_fact(self, conn: sqlite3.Connection, fact_id: int) -> dict | None:
        row = conn.execute(
            """
            SELECT id, session_id, canonical_key, value, normalized_value, confidence, status,
                   superseded_by, valid_to, decay_score
            FROM facts
            WHERE id = ?
            """,
            (fact_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "canonical_key": row["canonical_key"],
            "value": row["value"],
            "normalized_value": row["normalized_value"],
            "confidence": row["confidence"],
            "status": row["status"],
            "superseded_by": row["superseded_by"],
            "valid_to": row["valid_to"],
            "decay_score": row["decay_score"],
        }

    # Versioned upsert: same key + same value -> reinforce; same key + different value -> supersede old.
    def upsert_facts(
        self,
        session_id: str,
        facts: Iterable[FactItem],
        source_message_id: int | None = None,
    ) -> None:
        self.ensure_session(session_id)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for fact in facts:
                canonical_key = self._normalize_key(fact.key)
                normalized_value = self._normalize_value(fact.value)

                existing_exact = conn.execute(
                    """
                    SELECT id
                    FROM facts
                    WHERE session_id = ? AND canonical_key = ? AND normalized_value = ? AND status = 'active'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (session_id, canonical_key, normalized_value),
                ).fetchone()
                if existing_exact:
                    self._touch_fact(conn, existing_exact["id"], fact.confidence)
                    continue

                active_conflict = conn.execute(
                    """
                    SELECT id
                    FROM facts
                    WHERE session_id = ? AND canonical_key = ? AND status = 'active'
                    ORDER BY confidence DESC, id DESC
                    """,
                    (session_id, canonical_key),
                ).fetchall()

                for row in active_conflict:
                    conn.execute(
                        """
                        UPDATE facts
                        SET status = 'superseded',
                            superseded_by = NULL,
                            valid_to = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (row["id"],),
                    )

                cur = conn.execute(
                    """
                    INSERT INTO facts (
                        session_id,
                        canonical_key,
                        value,
                        normalized_value,
                        confidence,
                        status,
                        source_message_id
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                    """,
                    (
                        session_id,
                        canonical_key,
                        fact.value.strip(),
                        normalized_value,
                        fact.confidence,
                        source_message_id,
                    ),
                )
                new_id = int(cur.lastrowid)

                for row in active_conflict:
                    conn.execute(
                        """
                        UPDATE facts
                        SET superseded_by = ?
                        WHERE id = ?
                        """,
                        (new_id, row["id"]),
                    )

    def apply_decay(self, half_life_days: float, expire_threshold: float) -> None:
        # Time decay keeps stale memories from dominating retrieval forever.
        half_life = max(half_life_days, 0.1)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, confidence, last_seen_at
                FROM facts
                WHERE status = 'active'
                """
            ).fetchall()

            now = datetime.utcnow()
            for row in rows:
                try:
                    last_seen = datetime.fromisoformat(str(row["last_seen_at"]).replace("Z", ""))
                except ValueError:
                    continue
                age_days = max((now - last_seen).total_seconds() / 86400.0, 0.0)
                decay = math.pow(0.5, age_days / half_life)
                effective_score = float(row["confidence"]) * decay

                if effective_score < expire_threshold:
                    conn.execute(
                        """
                        UPDATE facts
                        SET status = 'expired',
                            decay_score = ?,
                            valid_to = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (decay, row["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE facts SET decay_score = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (decay, row["id"]),
                    )

    def list_facts(
        self,
        session_id: str,
        limit: int = 10,
        include_inactive: bool = False,
    ) -> list[FactItem]:
        status_filter = "WHERE session_id = ?"
        if not include_inactive:
            status_filter += " AND status = 'active'"
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, session_id, canonical_key, value, confidence, status, decay_score
                FROM facts
                {status_filter}
                ORDER BY (confidence * decay_score) DESC, updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [
            FactItem(
                session_id=row["session_id"],
                id=row["id"],
                key=row["canonical_key"],
                value=row["value"],
                confidence=row["confidence"],
                status=row["status"],
                decay_score=row["decay_score"],
            )
            for row in rows
        ]

    # Manual operations below are logged to support /facts undo in CLI.
    def add_fact_manual(
        self,
        session_id: str,
        key: str,
        value: str,
        confidence: float = 0.9,
    ) -> bool:
        self.ensure_session(session_id)
        canonical_key = self._normalize_key(key)
        normalized_value = self._normalize_value(value)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing_exact = conn.execute(
                """
                SELECT id FROM facts
                WHERE session_id = ? AND canonical_key = ? AND normalized_value = ? AND status = 'active'
                ORDER BY id DESC LIMIT 1
                """,
                (session_id, canonical_key, normalized_value),
            ).fetchone()
            if existing_exact:
                self._touch_fact(conn, existing_exact["id"], confidence)
                self._record_action(
                    conn,
                    "touch",
                    {"fact_id": int(existing_exact["id"]), "confidence": confidence},
                )
                return True

            superseded_ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM facts WHERE session_id = ? AND canonical_key = ? AND status = 'active'",
                    (session_id, canonical_key),
                ).fetchall()
            ]
            for old_id in superseded_ids:
                conn.execute(
                    """
                    UPDATE facts
                    SET status = 'superseded', superseded_by = NULL, valid_to = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (old_id,),
                )
            cur = conn.execute(
                """
                INSERT INTO facts (session_id, canonical_key, value, normalized_value, confidence, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (session_id, canonical_key, value.strip(), normalized_value, confidence),
            )
            new_id = int(cur.lastrowid)

            for old_id in superseded_ids:
                conn.execute(
                    """
                    UPDATE facts
                    SET superseded_by = ?
                    WHERE id = ?
                    """,
                    (new_id, old_id),
                )

            self._record_action(
                conn,
                "add",
                {
                    "new_id": new_id,
                    "superseded_ids": superseded_ids,
                },
            )
            return True

    def edit_fact(self, fact_id: int, new_value: str, confidence: float | None = None) -> bool:
        normalized_value = self._normalize_value(new_value)
        with self._conn() as conn:
            before = self._snapshot_fact(conn, fact_id)
            row = conn.execute(
                "SELECT id, session_id, canonical_key FROM facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
            if not row:
                return False
            duplicate = conn.execute(
                """
                SELECT id FROM facts
                WHERE session_id = ? AND canonical_key = ? AND normalized_value = ? AND status = 'active' AND id != ?
                LIMIT 1
                """,
                (row["session_id"], row["canonical_key"], normalized_value, fact_id),
            ).fetchone()
            if duplicate:
                return False
            if confidence is None:
                conn.execute(
                    """
                    UPDATE facts
                    SET value = ?, normalized_value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_value.strip(), normalized_value, fact_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE facts
                    SET value = ?, normalized_value = ?, confidence = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (new_value.strip(), normalized_value, confidence, fact_id),
                )
            after = self._snapshot_fact(conn, fact_id)
            self._record_action(conn, "edit", {"before": before, "after": after})
            return True

    def expire_fact(self, fact_id: int) -> bool:
        with self._conn() as conn:
            before = self._snapshot_fact(conn, fact_id)
            cur = conn.execute(
                """
                UPDATE facts
                SET status = 'expired', valid_to = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (fact_id,),
            )
            if cur.rowcount > 0:
                after = self._snapshot_fact(conn, fact_id)
                self._record_action(conn, "expire", {"before": before, "after": after})
            return cur.rowcount > 0

    def delete_fact(self, fact_id: int) -> bool:
        with self._conn() as conn:
            before = self._snapshot_fact(conn, fact_id)
            cur = conn.execute(
                """
                UPDATE facts
                SET status = 'deleted', valid_to = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status != 'deleted'
                """,
                (fact_id,),
            )
            if cur.rowcount > 0:
                after = self._snapshot_fact(conn, fact_id)
                self._record_action(conn, "delete", {"before": before, "after": after})
            return cur.rowcount > 0

    def supersede_fact(self, fact_id: int, new_value: str, confidence: float = 0.8) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT session_id, canonical_key FROM facts WHERE id = ?",
                (fact_id,),
            ).fetchone()
            if not row:
                return False
        return self.add_fact_manual(
            session_id=row["session_id"],
            key=row["canonical_key"],
            value=new_value,
            confidence=confidence,
        )

    def undo_last_fact_action(self) -> bool:
        # Undo only targets manual governance operations, newest first.
        with self._conn() as conn:
            action = conn.execute(
                "SELECT id, action_type, payload_json FROM fact_actions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not action:
                return False

            action_id = int(action["id"])
            action_type = str(action["action_type"])
            payload = json.loads(str(action["payload_json"]))

            if action_type == "add":
                new_id = int(payload["new_id"])
                conn.execute("DELETE FROM facts WHERE id = ?", (new_id,))
                for old_id in payload.get("superseded_ids", []):
                    conn.execute(
                        """
                        UPDATE facts
                        SET status = 'active', superseded_by = NULL, valid_to = NULL, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (int(old_id),),
                    )
            elif action_type == "touch":
                return False
            elif action_type in {"edit", "expire", "delete"}:
                before = payload.get("before")
                if not before:
                    return False
                conn.execute(
                    """
                    UPDATE facts
                    SET value = ?,
                        normalized_value = ?,
                        confidence = ?,
                        status = ?,
                        superseded_by = ?,
                        valid_to = ?,
                        decay_score = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        before["value"],
                        before["normalized_value"],
                        before["confidence"],
                        before["status"],
                        before["superseded_by"],
                        before["valid_to"],
                        before["decay_score"],
                        before["id"],
                    ),
                )
            else:
                return False

            conn.execute("DELETE FROM fact_actions WHERE id = ?", (action_id,))
            return True
