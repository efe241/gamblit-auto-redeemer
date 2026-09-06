"""
Unit tests for RedeemQueue and Worker processing.
"""
import pytest
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from app.queue import RedeemQueue
from app.worker import RedeemWorker
from app.database import Database
from app.metrics import MetricsTracker
from app.config import Config
from app.models import ParsedCode, RedeemResult, RedeemStatus, RedeemLatency

TEST_DB_PATH = "data/test_worker.db"


@pytest.fixture
async def setup_env():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    db = Database(db_path=TEST_DB_PATH)
    await db.connect()
    queue = RedeemQueue(db=db)
    await queue.initialize()
    metrics = MetricsTracker()
    cfg = Config()

    mock_client = MagicMock()
    mock_client.redeem_code = AsyncMock()

    worker = RedeemWorker(
        queue=queue,
        client=mock_client,
        db=db,
        metrics=metrics,
        config=cfg,
    )

    yield queue, worker, mock_client, db, metrics

    await worker.stop()
    await db.close()

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_queue_duplicate_protection(setup_env):
    queue, worker, client, db, metrics = setup_env

    item1 = ParsedCode(code="WORKER_TEST", message_id=1, channel_id=2, guild_id=3, author_id=4)
    item2 = ParsedCode(code="WORKER_TEST", message_id=5, channel_id=2, guild_id=3, author_id=6)

    # First should succeed
    assert await queue.enqueue(item1) is True

    # Duplicate should be rejected by RAM cache
    assert await queue.enqueue(item2) is False
    assert queue.qsize == 1


@pytest.mark.asyncio
async def test_worker_processes_code(setup_env):
    queue, worker, client, db, metrics = setup_env

    client.redeem_code.return_value = RedeemResult(
        code="WORKER_SUCCESS",
        status=RedeemStatus.SUCCESS,
        message="Code redeemed",
        latency=RedeemLatency(t0_discord_received=1.0, t3_response_received=1.05),
    )

    await worker.start()

    item = ParsedCode(code="WORKER_SUCCESS", message_id=10, channel_id=20, guild_id=30, author_id=40)
    await queue.enqueue(item)

    # Wait for queue to drain
    await asyncio.sleep(0.1)

    assert metrics.total_success == 1
    assert metrics.total_failed == 0
    client.redeem_code.assert_called_once()
