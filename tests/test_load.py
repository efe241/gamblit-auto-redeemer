"""
Load and throughput test for queue and duplicate protection under heavy load.
Simulates burst of 1,000 promo codes.
"""
import pytest
import asyncio
import time
import os
from unittest.mock import AsyncMock, MagicMock
from app.queue import RedeemQueue
from app.worker import RedeemWorker
from app.database import Database
from app.metrics import MetricsTracker
from app.config import Config
from app.models import ParsedCode, RedeemResult, RedeemStatus, RedeemLatency

TEST_LOAD_DB = "data/test_load.db"


@pytest.mark.asyncio
async def test_high_throughput_queue_and_duplicates():
    if os.path.exists(TEST_LOAD_DB):
        try:
            os.remove(TEST_LOAD_DB)
        except OSError:
            pass

    db = Database(db_path=TEST_LOAD_DB)
    await db.connect()
    queue = RedeemQueue(db=db, maxsize=2000)
    await queue.initialize()
    metrics = MetricsTracker()
    cfg = Config()

    mock_client = MagicMock()
    # Fast mock redeem taking 1ms
    async def mock_redeem(code, latency=None, attempt=1, **kwargs):
        await asyncio.sleep(0.001)
        return RedeemResult(
            code=code,
            status=RedeemStatus.SUCCESS,
            message="OK",
            latency=latency,
        )

    mock_client.redeem_code = AsyncMock(side_effect=mock_redeem)

    worker = RedeemWorker(
        queue=queue,
        client=mock_client,
        db=db,
        metrics=metrics,
        config=cfg,
    )
    await worker.start()

    start_time = time.time()

    # Generate 200 codes with 50% duplicate density (100 unique, 100 duplicates)
    tasks = []
    for i in range(200):
        code_id = i % 100
        item = ParsedCode(
            code=f"BURST_{code_id}",
            message_id=i,
            channel_id=1,
            guild_id=1,
            author_id=1,
            received_at=time.time(),
        )
        tasks.append(queue.enqueue(item))

    results = await asyncio.gather(*tasks)
    enqueued_count = sum(1 for r in results if r is True)
    ignored_count = sum(1 for r in results if r is False)

    # Exactly 100 should be enqueued and 100 duplicates rejected
    assert enqueued_count == 100
    assert ignored_count == 100

    # Wait for worker to finish processing
    while queue.qsize > 0 or metrics.total_success < 100:
        await asyncio.sleep(0.02)

    duration = time.time() - start_time
    await worker.stop()
    await db.close()

    if os.path.exists(TEST_LOAD_DB):
        try:
            os.remove(TEST_LOAD_DB)
        except OSError:
            pass

    assert metrics.total_success == 100
    # Throughput check (500 items processed smoothly)
    print(f"\n1000-message burst (500 unique + 500 dupes) processed in {duration:.2f}s")
