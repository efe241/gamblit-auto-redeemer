"""
Unit tests for Database interface and crash recovery.
"""
import pytest
import os
from app.database import Database
from app.models import ParsedCode, RedeemStatus, RedeemResult, RedeemLatency

TEST_DB_PATH = "data/test_gamblit.db"


@pytest.fixture
async def db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    database = Database(db_path=TEST_DB_PATH)
    await database.connect()
    yield database
    await database.close()

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_register_and_duplicate(db: Database):
    item = ParsedCode(
        code="DUPTEST123",
        message_id=1,
        channel_id=2,
        guild_id=3,
        author_id=4,
    )
    # First insert -> True
    assert await db.register_new_code(item) is True

    # Duplicate insert -> False
    assert await db.register_new_code(item) is False
    assert await db.is_code_present("DUPTEST123") is True


@pytest.mark.asyncio
async def test_mark_and_update_result(db: Database):
    item = ParsedCode(
        code="STATUS123",
        message_id=1,
        channel_id=2,
        guild_id=3,
        author_id=4,
    )
    await db.register_new_code(item)
    await db.mark_processing("STATUS123")

    result = RedeemResult(
        code="STATUS123",
        status=RedeemStatus.SUCCESS,
        message="Claimed successfully",
        latency=RedeemLatency(t0_discord_received=1.0, t3_response_received=1.05),
        attempts=1,
    )
    await db.update_redeem_result(result)

    stats = await db.get_stats()
    assert stats["total_codes"] == 1
    assert stats["successful"] == 1
    assert stats["last_code"] == "STATUS123"


@pytest.mark.asyncio
async def test_crash_recovery(db: Database):
    item = ParsedCode(
        code="CRASH_CODE",
        message_id=10,
        channel_id=20,
        guild_id=30,
        author_id=40,
    )
    await db.register_new_code(item)
    await db.mark_processing("CRASH_CODE")

    # Simulate crash by closing and reopening
    await db.close()

    db2 = Database(db_path=TEST_DB_PATH)
    await db2.connect()

    async with db2._connection.cursor() as cursor:
        await cursor.execute("SELECT status FROM codes WHERE code = 'CRASH_CODE'")
        row = await cursor.fetchone()
        # Should have recovered from PROCESSING to UNKNOWN
        assert row["status"] == "UNKNOWN"

    await db2.close()
