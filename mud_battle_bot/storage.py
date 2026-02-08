from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from mud_battle_bot.models import BattleState


class SQLiteBattleRepository:
    """Read-through cache with SQLite as source of truth."""

    def __init__(self, db_path: str = "data/battles.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[int, BattleState] = {}
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS battles (
                chat_id INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def load_battle(self, chat_id: int) -> Optional[BattleState]:
        cached = self._cache.get(chat_id)
        if cached is not None:
            return cached

        row = self._conn.execute(
            "SELECT state_json FROM battles WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        state = BattleState.from_dict(data)
        self._cache[chat_id] = state
        return state

    def save_battle(self, chat_id: int, state: BattleState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        updated_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO battles(chat_id, state_json, updated_at)
            VALUES(?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (chat_id, payload, updated_at),
        )
        self._conn.commit()
        self._cache[chat_id] = state

    def delete_battle(self, chat_id: int) -> None:
        self._conn.execute("DELETE FROM battles WHERE chat_id = ?", (chat_id,))
        self._conn.commit()
        self._cache.pop(chat_id, None)
