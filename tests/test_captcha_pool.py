import pytest
from unittest.mock import patch, AsyncMock
from app.config import Config
from app.captcha_pool import CaptchaPool

@pytest.mark.asyncio
async def test_pool_ttl_and_invalidation():
    cfg = Config()
    pool = CaptchaPool(config=cfg)
    assert pool.is_token_valid is False
    assert await pool.get_token() == ''
    pool.set_token('P0_TEST_123')
    assert pool.is_token_valid is True
    assert pool.remaining_seconds > 90
    assert await pool.get_token() == 'P0_TEST_123'
    pool.invalidate()
    assert pool.is_token_valid is False
    assert await pool.get_token() == ''

@pytest.mark.asyncio
async def test_auto_solve_capsolver_priority():
    cfg = Config()
    pool = CaptchaPool(config=cfg)
    pool.capsolver_api_key = 'CS_KEY'
    pool.twocaptcha_api_key = '2C_KEY'
    with patch.object(pool, 'solve_capsolver', new_callable=AsyncMock) as mock_cs, patch.object(pool, 'solve_2captcha', new_callable=AsyncMock) as mock_2c:
        mock_cs.return_value = 'CS_TOKEN'
        mock_2c.return_value = '2C_TOKEN'
        token = await pool.auto_solve_once()
        assert token == 'CS_TOKEN'
        mock_cs.assert_called_once()
        mock_2c.assert_not_called()

@pytest.mark.asyncio
async def test_auto_solve_fallback_to_twocaptcha():
    cfg = Config()
    pool = CaptchaPool(config=cfg)
    pool.capsolver_api_key = 'CS_KEY'
    pool.twocaptcha_api_key = '2C_KEY'
    with patch.object(pool, 'solve_capsolver', new_callable=AsyncMock) as mock_cs, patch.object(pool, 'solve_2captcha', new_callable=AsyncMock) as mock_2c:
        mock_cs.return_value = None
        mock_2c.return_value = '2C_TOKEN'
        token = await pool.auto_solve_once()
        assert token == '2C_TOKEN'
        mock_cs.assert_called_once()
        mock_2c.assert_called_once()
