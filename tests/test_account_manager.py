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
    assert default_acc.name == "Ana Hesap (efe2424)"

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
