import pytest
import os
import json
from pathlib import Path
from app.config import Config
from app.account_manager import AccountManager

@pytest.mark.asyncio
async def test_account_manager_crud(tmp_path):
    json_file = str(tmp_path / "accounts.json")
    cfg = Config(raw_cookies='{"sid": "test_sid"}')
    mgr = AccountManager(config=cfg, data_path=json_file)

    # 1. Check auto-import of default account
    assert len(mgr.accounts) == 1
    default_acc = mgr.accounts["acc_default"]
    assert "Ana Hesap" in default_acc.name

    # 2. Add new account
    acc2 = await mgr.add_account("Hesap 2", '{"sid": "test_sid_2"}')
    assert len(mgr.accounts) == 2
    assert acc2.name == "Hesap 2"

    # 3. Toggle account
    await mgr.toggle_account(acc2.id)
    assert mgr.accounts[acc2.id].enabled is False
    await mgr.toggle_account(acc2.id)
    assert mgr.accounts[acc2.id].enabled is True

    # 4. Summary
    summary = mgr.get_summary()
    assert summary["total_accounts"] == 2

    # 5. Remove account
    ok = await mgr.remove_account(acc2.id)
    assert ok is True
    assert len(mgr.accounts) == 1

    await mgr.close_all()


def test_gamblit_level_calculation():
    from app.gamblit_client import calculate_gamblit_level, xp_required_for_level

    # Check boundaries
    assert calculate_gamblit_level(0) == 1
    assert calculate_gamblit_level(-100) == 1
    assert calculate_gamblit_level(None) == 1

    # Level 5 threshold is 2187.5
    assert calculate_gamblit_level(2187.0) == 4
    assert calculate_gamblit_level(2187.5) == 5

    # Known live user XP (ragenoisy: ~77,255,941.59 XP -> Level 135)
    assert calculate_gamblit_level(77255941.59) == 135


@pytest.mark.asyncio
async def test_numbered_cookies_env_auto_import(tmp_path, monkeypatch):
    json_file = str(tmp_path / "accounts_numbered.json")
    
    # Set COOKIE1, COOKIE2, COOKIE3 in environment
    monkeypatch.setenv("COOKIE1", "sid=cookie_acc_1; _vid_t=token1")
    monkeypatch.setenv("COOKIE2", "sid=cookie_acc_2; _vid_t=token2")
    monkeypatch.setenv("COOKIE3", "sid=cookie_acc_3; _vid_t=token3")
    monkeypatch.setenv("NAME1", "Ana Hesap (Tipisteme)")
    monkeypatch.setenv("NAME2", "Yan Hesap 1")

    cfg = Config()
    mgr = AccountManager(config=cfg, data_path=json_file)

    assert len(mgr.accounts) == 3
    assert "acc_1" in mgr.accounts
    assert "acc_2" in mgr.accounts
    assert "acc_3" in mgr.accounts

    assert mgr.accounts["acc_1"].name == "Ana Hesap (Tipisteme)"
    assert mgr.accounts["acc_1"].raw_cookies == "sid=cookie_acc_1; _vid_t=token1"
    assert mgr.accounts["acc_2"].name == "Yan Hesap 1"
    assert mgr.accounts["acc_2"].raw_cookies == "sid=cookie_acc_2; _vid_t=token2"
    assert mgr.accounts["acc_3"].name == "Hesap 3"

    await mgr.close_all()


@pytest.mark.asyncio
async def test_bulk_add_and_verify_all(tmp_path):
    from unittest.mock import AsyncMock
    from app.models import AccountProfile
    from app.captcha_pool import CaptchaPool

    json_file = str(tmp_path / "accounts_bulk.json")
    cfg = Config(raw_cookies="")
    mgr = AccountManager(config=cfg, data_path=json_file)

    bulk_text = """
    sid=bulk_1; _vid_t=tok1
    sid=bulk_2; _vid_t=tok2
    {"sid": "bulk_3"}
    """
    added = await mgr.add_accounts_bulk(bulk_text)
    assert len(added) == 3
    assert len(mgr.accounts) == 3

    # Mock verify on all accounts
    for acc in mgr.accounts.values():
        acc.client.connect_ws = AsyncMock(return_value=True)
        acc.client._connected = True
        acc.client.get_profile = AsyncMock(return_value=AccountProfile(
            username=f"User_{acc.id}",
            level=42,
            balance_dl=1250,
            is_authenticated=True,
        ))

    summary = await mgr.verify_all()
    assert summary["total_accounts"] == 3
    assert summary["connected_accounts"] == 3

    # Test CaptchaPool multi-token consumption
    pool = CaptchaPool(config=cfg, account_manager=mgr)
    pool.set_token("token_1")
    pool.set_token("token_2")
    pool.set_token("token_3")

    popped = await pool.consume_tokens(count=3)
    assert len(popped) == 3
    assert popped == ["token_1", "token_2", "token_3"]
    assert pool.valid_token_count == 0

    await mgr.close_all()
