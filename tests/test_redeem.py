"""
Integration tests for GamblitClient against the MockGamblitServer.
Verifies all HTTP response codes, latency metrics, and error categorizations.
"""
import pytest
import pytest_asyncio
import json
from tests.mock_gamblit import MockGamblitServer
from app.gamblit_client import GamblitClient
from app.config import Config
from app.models import RedeemStatus, RedeemLatency


@pytest_asyncio.fixture
async def mock_server():
    server = MockGamblitServer(host="127.0.0.1", port=8999)
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture
async def client(mock_server):
    config = Config(
        gamblit_base_url=mock_server.base_url,
        raw_cookies=json.dumps({"cf_clearance": "valid_token", "_iidt": "valid_iidt"}),
        redeem_endpoints=["/api/promo/redeem"],
        connect_timeout_sec=1.0,
        read_timeout_sec=1.0,
    )
    gamblit_client = GamblitClient(config=config)
    yield gamblit_client
    await gamblit_client.close()


@pytest.mark.asyncio
async def test_successful_redeem(client: GamblitClient):
    latency = RedeemLatency(t0_discord_received=1.0)
    result = await client.redeem_code("SUCCESS2026", latency=latency)

    assert result.success is True
    assert result.status == RedeemStatus.SUCCESS
    assert "successfully" in result.message
    assert result.latency.http_request_ms > 0.0


@pytest.mark.asyncio
async def test_expired_code(client: GamblitClient):
    result = await client.redeem_code("EXPIRED_CODE")
    assert result.status == RedeemStatus.EXPIRED


@pytest.mark.asyncio
async def test_already_used_code(client: GamblitClient):
    result = await client.redeem_code("ALREADY_USED")
    assert result.status == RedeemStatus.ALREADY_USED


@pytest.mark.asyncio
async def test_not_eligible_level(client: GamblitClient):
    result = await client.redeem_code("HIGH_LEVEL")
    assert result.status == RedeemStatus.NOT_ELIGIBLE


@pytest.mark.asyncio
async def test_rate_limit(client: GamblitClient):
    result = await client.redeem_code("RATE_LIMIT_TEST")
    assert result.status == RedeemStatus.RATE_LIMITED
    assert result.retry_after == 1.0


@pytest.mark.asyncio
async def test_server_error(client: GamblitClient):
    result = await client.redeem_code("SERVER_ERROR")
    assert result.status == RedeemStatus.SERVER_ERROR


@pytest.mark.asyncio
async def test_invalid_code(client: GamblitClient):
    result = await client.redeem_code("NON_EXISTENT_XYZ")
    assert result.status == RedeemStatus.INVALID_CODE


@pytest.mark.asyncio
async def test_auth_failure(mock_server):
    # Create client with no cookies
    bad_config = Config(
        gamblit_base_url=mock_server.base_url,
        raw_cookies="{}",
        redeem_endpoints=["/api/promo/redeem"],
    )
    bad_client = GamblitClient(config=bad_config)
    result = await bad_client.redeem_code("SUCCESS2026")
    await bad_client.close()

    assert result.status == RedeemStatus.AUTH_ERROR
