"""
In-memory async queue with two-layer duplicate protection (RAM Set + DB).
"""
import asyncio
import logging
from typing import Set, Optional
from app.models import ParsedCode
from app.database import Database

log = logging.getLogger("gamblit_redeemer.queue")


class RedeemQueue:
    def __init__(self, db: Database, maxsize: int = 1000):
        self.db = db
        self._queue: asyncio.Queue[ParsedCode] = asyncio.Queue(maxsize=maxsize)
        self._seen_codes: Set[str] = set()
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Pre-loads known codes from database into RAM cache on startup."""
        stored_codes = await self.db.load_seen_codes()
        self._seen_codes.update(stored_codes)
        log.info(f"RedeemQueue initialized with {len(self._seen_codes)} cached codes from DB.")

    async def enqueue(self, item: ParsedCode) -> bool:
        """
        Fast duplicate check and enqueue:
        1. RAM Cache check (O(1) set lookup)
        2. Database persistence check
        3. Push to asyncio.Queue
        Returns True if enqueued, False if duplicate.
        """
        code_upper = item.code.upper()

        # If it's a multi-level drop, check if all codes were already seen
        if item.level_codes:
            codes_in_drop = [c[1].upper() for c in item.level_codes]
            async with self._lock:
                if all(c in self._seen_codes for c in codes_in_drop):
                    log.info(f"[Duplicate Ignored] All codes in drop already processed (RAM cache).")
                    return False
                for c in codes_in_drop:
                    self._seen_codes.add(c)

            await self.db.register_new_code(item)
            try:
                self._queue.put_nowait(item)
                log.info(f"[Enqueued] Multi-level drop with {len(codes_in_drop)} codes added to redeem queue.")
                return True
            except asyncio.QueueFull:
                log.error("Redeem queue is full! Dropping multi-level drop.")
                return False

        # Layer 1: Instant RAM check
        async with self._lock:
            if code_upper in self._seen_codes:
                log.info(f"[Duplicate Ignored] Code '{code_upper}' already processed (RAM cache).")
                return False
            self._seen_codes.add(code_upper)

        # Layer 2: Persistent Database check & registration
        inserted = await self.db.register_new_code(item)
        if not inserted:
            log.info(f"[Duplicate Ignored] Code '{code_upper}' already present in database.")
            return False

        # Layer 3: Enqueue for async worker
        try:
            self._queue.put_nowait(item)
            log.info(f"[Enqueued] Code '{code_upper}' added to redeem queue.")
            return True
        except asyncio.QueueFull:
            log.error(f"Redeem queue is full! Dropping code: {code_upper}")
            return False

    async def dequeue(self) -> ParsedCode:
        """Pulls next code from queue for worker execution."""
        return await self._queue.get()

    def task_done(self):
        """Marks current queue task as processed."""
        self._queue.task_done()

    @property
    def qsize(self) -> int:
        return self._queue.qsize()
