"""
Phased test suite for 7-account multi-level redemption ordered by level (highest to lowest)
and captcha efficiency.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from app.models import ParsedCode, RedeemStatus, RedeemResult, RedeemLatency, AccountProfile
from app.parser import CodeParser
from app.config import Config
from app.account_manager import AccountManager, ManagedAccount
from app.captcha_pool import CaptchaPool
from app.queue import RedeemQueue
from app.database import Database
from app.worker import RedeemWorker


# =========================================================================
# PHASE 1: Multi-Level Drop Parsing & Descending Order Tests
# =========================================================================

def test_phase1_drop_parser_descending_order():
    discord_drop_content = """
    🚨 **MEGA DROP ALERT** 🚨
    :unlock: LEVEL 175+ Use the code `DROP175` to claim 500 DL
    :unlock: LEVEL 150+ Use the code DROP150 to claim 400 DL
    :unlock: LEVEL 125+ Use the code DROP125 to claim 300 DL
    :unlock: LEVEL 100+ Use the code **DROP100** to claim 200 DL
    :unlock: LEVEL 80+  Use the code DROP80 to claim 150 DL
    :unlock: LEVEL 60+  Use the code DROP60 to claim 100 DL
    :unlock: LEVEL 40+  Use the code DROP40 to claim 75 DL
    :unlock: LEVEL 25+  Use the code DROP25 to claim 40 DL
    :unlock: LEVEL 5+   Use the code DROP5 to claim 10 DL
    """

    level_codes = CodeParser.extract_level_codes(discord_drop_content)

    # 1. Ensure all 9 codes were extracted
    assert len(level_codes) == 9

    # 2. Ensure strictly descending order (highest required level first)
    expected_order = [
        (175, "DROP175"),
        (150, "DROP150"),
        (125, "DROP125"),
        (100, "DROP100"),
        (80, "DROP80"),
        (60, "DROP60"),
        (40, "DROP40"),
        (25, "DROP25"),
        (5, "DROP5"),
    ]
    assert level_codes == expected_order

    # 3. Test parse_drop_message with max_level filtering
    parsed_drop = CodeParser.parse_drop_message(
        content=discord_drop_content,
        message_id=111,
        channel_id=222,
        guild_id=333,
        author_id=444,
        max_level=125,  # Highest account level in team is 125
    )
    assert parsed_drop is not None
    # 175+ and 150+ are automatically filtered out because max_level is 125
    assert parsed_drop.code == "DROP125"
    assert parsed_drop.required_level == 125
    assert len(parsed_drop.level_codes) == 7
    assert parsed_drop.level_codes[0] == (125, "DROP125")
    assert parsed_drop.level_codes[-1] == (5, "DROP5")


# =========================================================================
# PHASE 2: 7 Accounts Concurrently Claiming Highest to Lowest Eligible Codes
# =========================================================================

@pytest.mark.asyncio
async def test_phase2_seven_accounts_redeem_drop_highest_to_lowest(tmp_path):
    json_file = str(tmp_path / "accounts_7.json")
    cfg = Config()
    mgr = AccountManager(config=cfg, data_path=json_file)

    levels = [180, 135, 90, 42, 30, 15, 3]
    mgr.accounts.clear()

    for i, lvl in enumerate(levels, start=1):
        acc = ManagedAccount(
            account_id=f"acc_{i}",
            name=f"Hesap {i} (Lvl {lvl})",
            cookies=f'{{"sid": "cookie_{i}"}}',
            enabled=True,
            config=cfg,
        )
        acc.client._profile = AccountProfile(
            username=f"User_{i}",
            level=lvl,
            is_authenticated=True,
        )
        mgr.accounts[acc.id] = acc

    assert len(mgr.accounts) == 7
    assert mgr.get_max_level() == 180

    drop_codes = [
        (175, "CODE175"),
        (150, "CODE150"),
        (125, "CODE125"),
        (100, "CODE100"),
        (80, "CODE80"),
        (60, "CODE60"),
        (40, "CODE40"),
        (25, "CODE25"),
        (5, "CODE5"),
    ]

    redeemed_sequences = {acc.id: [] for acc in mgr.accounts.values()}

    async def mock_redeem(acc_id, code, **kwargs):
        redeemed_sequences[acc_id].append(code)
        return RedeemResult(
            code=code,
            status=RedeemStatus.SUCCESS,
            message="Claimed WL!",
        )

    for acc in mgr.accounts.values():
        acc.client.redeem_code = MagicMock(
            side_effect=lambda c, aid=acc.id, **kwargs: mock_redeem(aid, c, **kwargs)
        )

    results = await mgr.redeem_drop(drop_codes)

    # Verify Account 1 (Level 180): Eligible for ALL 9 codes, starting with CODE175 down to CODE5
    assert redeemed_sequences["acc_1"] == [
        "CODE175", "CODE150", "CODE125", "CODE100", "CODE80", "CODE60", "CODE40", "CODE25", "CODE5"
    ]

    # Verify Account 2 (Level 135): Eligible for 125+ down to 5+ (skips 175 and 150)
    assert redeemed_sequences["acc_2"] == [
        "CODE125", "CODE100", "CODE80", "CODE60", "CODE40", "CODE25", "CODE5"
    ]

    # Verify Account 3 (Level 90): Eligible for 80+ down to 5+
    assert redeemed_sequences["acc_3"] == [
        "CODE80", "CODE60", "CODE40", "CODE25", "CODE5"
    ]

    # Verify Account 4 (Level 42, like user's main): Eligible for 40+, 25+, 5+
    assert redeemed_sequences["acc_4"] == [
        "CODE40", "CODE25", "CODE5"
    ]

    # Verify Account 5 (Level 30): Eligible for 25+, 5+
    assert redeemed_sequences["acc_5"] == [
        "CODE25", "CODE5"
    ]

    # Verify Account 6 (Level 15): Eligible only for 5+
    assert redeemed_sequences["acc_6"] == [
        "CODE5"
    ]

    # Verify Account 7 (Level 3): NOT eligible for any codes, makes 0 requests!
    assert redeemed_sequences["acc_7"] == []

    await mgr.close_all()


# =========================================================================
# PHASE 3: Captcha Token Zero-Waste & Challenge Consumption Tests
# =========================================================================

@pytest.mark.asyncio
async def test_phase3_captcha_zero_waste_and_atomic_consumption(tmp_path):
    cfg = Config()
    pool = CaptchaPool(config=cfg)

    # Initially empty pool
    assert await pool.consume_token() is None

    # Inject a token
    pool.set_token("CAPTCHA_TOKEN_XYZ_1")
    assert pool.is_token_valid is True

    # 1. Atomic consume: First account takes the token
    tok1 = await pool.consume_token()
    assert tok1 == "CAPTCHA_TOKEN_XYZ_1"

    # 2. Token is now consumed and pool is empty (no double-spend!)
    tok2 = await pool.consume_token()
    assert tok2 is None
    assert pool.is_token_valid is False


@pytest.mark.asyncio
async def test_phase3_multi_token_buffer_eliminates_15s_delay():
    cfg = Config()
    pool = CaptchaPool(config=cfg)

    # Pre-warm 7 tokens into the pool (simulating 7 pre-solved captchas)
    for i in range(1, 8):
        pool.set_token(f"PRE_SOLVED_TOKEN_{i}")

    assert pool.valid_token_count == 7

    # 7 accounts concurrently request tokens at the EXACT SAME INSTANT
    t_start = asyncio.get_event_loop().time()
    results = await asyncio.gather(*[pool.consume_token() for _ in range(7)])
    t_end = asyncio.get_event_loop().time()

    elapsed_ms = (t_end - t_start) * 1000.0

    # 1. Ensure lightning speed: All 7 accounts got tokens in < 5 milliseconds total (0.1ms each!)
    assert elapsed_ms < 10.0, f"Token retrieval took too long: {elapsed_ms} ms"

    # 2. Ensure all 7 tokens were retrieved and every single one is unique (zero duplicate tokens)
    assert len(results) == 7
    assert None not in results
    assert len(set(results)) == 7

    # 3. Pool is now safely emptied
    assert pool.valid_token_count == 0


# =========================================================================
# PHASE 4: End-to-End Worker & Queue Pipeline Test
# =========================================================================

@pytest.mark.asyncio
async def test_phase4_end_to_end_worker_drop_execution(tmp_path):
    db_path = str(tmp_path / "test_gamblit.db")
    db = Database(db_path=db_path)
    await db.connect()

    queue = RedeemQueue(db=db)
    await queue.initialize()

    cfg = Config()
    mgr = AccountManager(config=cfg, data_path=str(tmp_path / "acc.json"))
    mgr.accounts.clear()

    acc = ManagedAccount(
        account_id="test_acc",
        name="Test Account",
        cookies='{"sid": "cookie"}',
        enabled=True,
        config=cfg,
    )
    acc.client._profile = AccountProfile(username="TestAcc", level=50, is_authenticated=True)
    mgr.accounts[acc.id] = acc

    claimed_codes = []

    async def mock_redeem(code, **kwargs):
        claimed_codes.append(code)
        return RedeemResult(code=code, status=RedeemStatus.SUCCESS, message="Claimed!")

    acc.client.redeem_code = mock_redeem

    from app.metrics import MetricsTracker
    metrics = MetricsTracker()
    worker = RedeemWorker(
        queue=queue,
        client=acc.client,
        db=db,
        metrics=metrics,
        config=cfg,
        account_manager=mgr,
    )

    # Build a multi-level drop ParsedCode
    drop_item = ParsedCode(
        code="DROP60",
        message_id=999,
        channel_id=888,
        guild_id=777,
        author_id=666,
        required_level=60,
        level_codes=[(60, "DROP60"), (40, "DROP40"), (20, "DROP20")],
    )

    # Process drop through worker
    result = await worker.process_code(drop_item)
    assert result.status == RedeemStatus.SUCCESS

    # Account with Level 50 is eligible for 40+ and 20+ (skips 60+)
    # Must claim DROP40 first, then DROP20!
    assert claimed_codes == ["DROP40", "DROP20"]

    await mgr.close_all()
    await db.close()


@pytest.mark.asyncio
async def test_durum_page_and_api(tmp_path):
    from app.web_panel import WebPanel
    from app.config import Config
    from app.database import Database
    from app.metrics import MetricsTracker
    from app.queue import RedeemQueue
    from app.captcha_pool import CaptchaPool
    from app.account_manager import AccountManager, ManagedAccount
    from app.models import AccountProfile
    from unittest.mock import MagicMock
    import json

    cfg = Config()
    db = Database(str(tmp_path / "test_durum.db"))
    await db.connect()
    metrics = MetricsTracker()
    queue = RedeemQueue(db=db)
    captcha_pool = CaptchaPool(config=cfg)
    mgr = AccountManager(config=cfg, data_path=str(tmp_path / "accounts.json"))
    mgr.accounts.clear()

    acc1 = ManagedAccount("acc_main", "Main", "c1", True, cfg)
    acc1.client._profile = AccountProfile(username="Tipisteme", level=42, balance_dl=508.42, is_authenticated=True)
    mgr.accounts[acc1.id] = acc1

    panel = WebPanel(
        config=cfg,
        client=acc1.client,
        db=db,
        metrics=metrics,
        queue=queue,
        captcha_pool=captcha_pool,
        account_manager=mgr,
    )

    req = MagicMock()
    resp_durum = await panel.handle_durum(req)
    assert resp_durum.status == 200
    assert "Gamblit Auto-Redeemer" in resp_durum.text
    assert "/api/durum" in resp_durum.text

    resp_api = await panel.handle_durum_api(req)
    assert resp_api.status == 200
    data = json.loads(resp_api.text)
    assert data["total_accounts"] == 1
    assert data["connected_accounts"] == 1
    assert data["total_dl"] == 5.08
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["username"] == "Tipisteme"
    assert data["accounts"][0]["level"] == 42

    # Test /sonuc before any run
    resp_sonuc_empty = await panel.handle_sonuc_api(req)
    data_empty = json.loads(resp_sonuc_empty.text)
    assert data_empty.get("status") == "none"

    resp_sonuc_html = await panel.handle_sonuc(req)
    assert resp_sonuc_html.status == 200
    assert "Test Redeem Sonuçları" in resp_sonuc_html.text

    # Mock redeem_code response
    from app.models import RedeemResult, RedeemStatus
    async def mock_expired_redeem(c, **kwargs):
        return RedeemResult(code=c, status=RedeemStatus.EXPIRED, message="Code has expired")

    acc1.client.redeem_code = mock_expired_redeem

    # Run test
    test_res = await panel.run_redeem_test("OLDDROP123")
    assert test_res["code"] == "OLDDROP123"
    assert test_res["accounts_count"] == 1
    assert test_res["accounts"][0]["badge_type"] == "warning"
    assert "Süresi Dolmuş" in test_res["accounts"][0]["badge_text"]

    # Verify /api/sonuc returns this test result
    resp_sonuc_filled = await panel.handle_sonuc_api(req)
    data_filled = json.loads(resp_sonuc_filled.text)
    assert data_filled["code"] == "OLDDROP123"
    assert len(data_filled["accounts"]) == 1

    # Verify /test redirects to /sonuc
    from aiohttp import web
    req_test = MagicMock()
    req_test.query = {"code": "OLDDROP123"}
    with pytest.raises(web.HTTPFound) as exc_info:
        await panel.handle_test_redeem(req_test)
    assert exc_info.value.location == "/sonuc"

    await db.close()
    await mgr.close_all()

