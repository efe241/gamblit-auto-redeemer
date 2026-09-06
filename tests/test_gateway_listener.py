import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from app.config import Config
from app.gateway_listener import DiscordGatewayListener
from app.queue import RedeemQueue
from app.metrics import MetricsTracker
from app.database import Database

@pytest.mark.asyncio
async def test_gateway_process_target_message():
    cfg = Config()
    cfg.discord_channel_id = 123456789
    cfg.discord_guild_id = 987654321

    queue = AsyncMock(spec=RedeemQueue)
    queue.enqueue = AsyncMock(return_value=True)
    metrics = MetricsTracker()
    db = AsyncMock(spec=Database)
    client = MagicMock()

    listener = DiscordGatewayListener(
        config=cfg,
        queue=queue,
        metrics=metrics,
        db=db,
        client=client
    )
    listener.user_id = '999999'

    # 1. Message from target channel with promo code
    target_payload = {
        'channel_id': '123456789',
        'guild_id': '987654321',
        'id': '111222',
        'content': 'LEVEL 5+ CODE: SECRET_PROMO_CODE',
        'author': {'id': '55555', 'username': 'DropBot'}
    }

    await listener._process_message_event(target_payload)

    queue.enqueue.assert_called_once()
    item = queue.enqueue.call_args[0][0]
    assert item.code == 'SECRET_PROMO_CODE'
    assert metrics.total_received == 1
    assert metrics.total_parsed == 1

@pytest.mark.asyncio
async def test_gateway_ignore_wrong_channel():
    cfg = Config()
    cfg.discord_channel_id = 123456789

    queue = AsyncMock(spec=RedeemQueue)
    metrics = MetricsTracker()
    db = AsyncMock(spec=Database)
    client = MagicMock()

    listener = DiscordGatewayListener(
        config=cfg,
        queue=queue,
        metrics=metrics,
        db=db,
        client=client
    )

    wrong_channel_payload = {
        'channel_id': '999999999',
        'id': '111223',
        'content': 'CODE: IGNORE_ME',
        'author': {'id': '55555', 'username': 'DropBot'}
    }

    await listener._process_message_event(wrong_channel_payload)
    queue.enqueue.assert_not_called()
