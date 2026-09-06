"""
Asynchronous SQLite database interface for Gamblit Promo Code Auto-Redeemer.
Provides duplicate checking, persistent code records, crash recovery, and event logging.
"""
import os
import json
import time
from pathlib import Path
from typing import Set, List, Optional, Dict, Any
import aiosqlite
from app.models import RedeemStatus, ParsedCode, RedeemResult


class Database:
    def __init__(self, db_path: str = "data/gamblit.db"):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """Opens database connection and creates tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._init_schema()
        await self._recover_unresolved_tasks()

    async def close(self):
        """Closes database connection gracefully."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _init_schema(self):
        """Initializes tables if they do not exist."""
        async with self._connection.cursor() as cursor:
            # Codes table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    message_id INTEGER,
                    channel_id INTEGER,
                    received_at REAL,
                    processed_at REAL,
                    status TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_attempt REAL,
                    latency_ms REAL,
                    response TEXT
                )
            """)
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_codes_code ON codes(code);")

            # Events table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    details TEXT
                )
            """)

            # Account snapshot table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    account_name TEXT,
                    level INTEGER,
                    balance_dl REAL,
                    last_check REAL,
                    status TEXT
                )
            """)
            await self._connection.commit()

    async def _recover_unresolved_tasks(self):
        """Crash recovery: Resets orphaned PROCESSING codes to UNKNOWN."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE codes
                SET status = 'UNKNOWN'
                WHERE status = 'PROCESSING'
            """)
            await self._connection.commit()

    async def load_seen_codes(self) -> Set[str]:
        """Loads all existing codes into RAM set for instant duplicate rejection."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("SELECT code FROM codes")
            rows = await cursor.fetchall()
            return {row["code"] for row in rows}

    async def is_code_present(self, code: str) -> bool:
        """Direct DB check if code exists."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("SELECT 1 FROM codes WHERE code = ? LIMIT 1", (code,))
            row = await cursor.fetchone()
            return row is not None

    async def register_new_code(self, parsed: ParsedCode) -> bool:
        """
        Inserts new code as 'NEW'.
        Returns True if inserted, False if already exists (duplicate).
        """
        try:
            async with self._connection.cursor() as cursor:
                await cursor.execute("""
                    INSERT INTO codes (
                        code, message_id, channel_id, received_at, status, attempts
                    ) VALUES (?, ?, ?, ?, ?, 0)
                """, (
                    parsed.code,
                    parsed.message_id,
                    parsed.channel_id,
                    parsed.received_at,
                    RedeemStatus.NEW.value,
                ))
                await self._connection.commit()
                return True
        except aiosqlite.IntegrityError:
            # Code already exists in database
            return False

    async def mark_processing(self, code: str):
        """Marks code as PROCESSING and bumps attempt count."""
        now = time.time()
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE codes
                SET status = ?, attempts = attempts + 1, last_attempt = ?
                WHERE code = ?
            """, (RedeemStatus.PROCESSING.value, now, code))
            await self._connection.commit()

    async def update_redeem_result(self, result: RedeemResult):
        """Updates code record with final/latest RedeemResult and latencies."""
        now = time.time()
        resp_json = json.dumps(result.response_data or {"message": result.message})
        latency_total = result.latency.total_ms

        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                UPDATE codes
                SET status = ?,
                    processed_at = ?,
                    latency_ms = ?,
                    response = ?,
                    attempts = ?
                WHERE code = ?
            """, (
                result.status.value,
                now,
                latency_total,
                resp_json,
                result.attempts,
                result.code,
            ))
            await self._connection.commit()

    async def log_event(self, event_type: str, details: Dict[str, Any]):
        """Logs an event into the events table."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO events (event_type, timestamp, details)
                VALUES (?, ?, ?)
            """, (event_type, time.time(), json.dumps(details)))
            await self._connection.commit()

    async def save_account_state(
        self,
        account_name: str,
        level: Optional[int],
        balance_dl: Optional[float],
        status: str,
    ):
        """Saves current account status."""
        async with self._connection.cursor() as cursor:
            await cursor.execute("""
                INSERT INTO account (id, account_name, level, balance_dl, last_check, status)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    account_name = excluded.account_name,
                    level = excluded.level,
                    balance_dl = excluded.balance_dl,
                    last_check = excluded.last_check,
                    status = excluded.status
            """, (account_name, level, balance_dl, time.time(), status))
            await self._connection.commit()

    async def get_stats(self) -> Dict[str, Any]:
        """Returns statistical overview for monitoring / status command."""
        stats = {
            "total_codes": 0,
            "successful": 0,
            "failed": 0,
            "last_code": None,
            "last_attempt": None,
            "avg_latency_ms": 0.0,
        }
        async with self._connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) as cnt FROM codes")
            row = await cursor.fetchone()
            stats["total_codes"] = row["cnt"] if row else 0

            await cursor.execute(
                "SELECT COUNT(*) as cnt FROM codes WHERE status = 'SUCCESS'"
            )
            row = await cursor.fetchone()
            stats["successful"] = row["cnt"] if row else 0

            stats["failed"] = stats["total_codes"] - stats["successful"]

            await cursor.execute("""
                SELECT code, last_attempt, latency_ms, status
                FROM codes
                ORDER BY id DESC
                LIMIT 1
            """)
            row = await cursor.fetchone()
            if row:
                stats["last_code"] = row["code"]
                stats["last_attempt"] = row["last_attempt"]
                stats["last_status"] = row["status"]
                stats["last_latency_ms"] = row["latency_ms"]

            await cursor.execute(
                "SELECT AVG(latency_ms) as avg_lat FROM codes WHERE latency_ms > 0"
            )
            row = await cursor.fetchone()
            if row and row["avg_lat"]:
                stats["avg_latency_ms"] = round(row["avg_lat"], 2)

        return stats
