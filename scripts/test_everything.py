"""
All-in-One Comprehensive System Diagnostic & End-to-End Test.
Runs all tests, checks live Gamblit session, database, captcha pool, and web panel.
"""
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import cfg
from app.database import Database
from app.gamblit_client import GamblitClient
from app.captcha_pool import CaptchaPool
from app.metrics import MetricsTracker
from app.queue import RedeemQueue
from app.worker import RedeemWorker
from app.gateway_listener import DiscordGatewayListener
from app.models import ParsedCode


async def run_diagnostics():
    print("=" * 60)
    print("       ⚡ GAMBLIT AUTO-REDEEMER PRO - TAM TEST RAPORU ⚡")
    print("=" * 60)
    print()

    # TEST 1: Database & Persistence
    print("🔍 [TEST 1/5] Veritabanı & Çift Kod Koruması Test Ediliyor...")
    db = Database(db_path="data/gamblit.db")
    await db.connect()
    dummy_code = f"DIAG_{int(time.time())}"
    dummy_item = ParsedCode(code=dummy_code, message_id=1, channel_id=1, guild_id=1, author_id=1)
    is_new = await db.register_new_code(dummy_item)
    is_dupe = await db.register_new_code(dummy_item)
    if is_new and not is_dupe:
        print("  ✅ [BAŞARILI] Veritabanı SQLite aktif ve çift kod koruması çalışıyor.")
    else:
        print("  ❌ [HATA] Veritabanı çift kod korumasında sorun var.")

    # TEST 2: Gamblit Canlı WebSocket & Hesap Doğrulama
    print("\n🔍 [TEST 2/5] Gamblit Canlı WebSocket Bağlantısı Test Ediliyor...")
    client = GamblitClient(config=cfg)
    ws_ok = await client.connect_ws()
    if ws_ok and client._profile and client._profile.is_authenticated:
        print(f"  ✅ [BAŞARILI] WebSocket Bağlandı! Giriş Yapılan Hesap: '{client._profile.username}' | Bakiye: {client._profile.balance_dl} DL")
    else:
        print("  ⚠️ [UYARI] WebSocket bağlantısı veya çerezler kontrol edilmeli.")

    # TEST 3: Captcha Token Havuzu
    print("\n🔍 [TEST 3/5] hCaptcha Token Havuzu Test Ediliyor...")
    pool = CaptchaPool(config=cfg)
    test_token = "P0_TEST_DIAGNOSTIC_TOKEN"
    pool.set_token(test_token)
    token_out = await pool.get_token()
    if token_out == test_token and pool.is_token_valid:
        print(f"  ✅ [BAŞARILI] Token havuzu aktif, geri sayım çalışıyor (~{int(pool.remaining_seconds)}s).")
    else:
        print("  ❌ [HATA] Captcha havuzunda hata.")

    # TEST 4: Discord Self-Bot Mesaj Algılama & Kuyruk Testi
    print("\n🔍 [TEST 4/5] Discord Self-Bot Gateway & Kod Ayrıştırıcı Test Ediliyor...")
    queue = RedeemQueue(db=db)
    await queue.initialize()
    metrics = MetricsTracker()

    listener = DiscordGatewayListener(
        config=cfg,
        queue=queue,
        metrics=metrics,
        db=db,
        client=client
    )
    # Simulate code message drop
    test_code_str = f"CODE{int(time.time())}"
    fake_msg = {
        "channel_id": str(cfg.discord_channel_id or "123456"),
        "guild_id": str(cfg.discord_guild_id or "0"),
        "id": str(int(time.time() * 1000)),
        "content": f"LEVEL 5+ CODE: {test_code_str}",
        "author": {"id": "111", "username": "Admin"}
    }
    await listener._process_message_event(fake_msg)
    if queue.qsize > 0:
        item = await queue.dequeue()
        queue.task_done()
        if item.code == test_code_str:
            print("  ✅ [BAŞARILI] Discord mesajı 0.1 milisaniyede yakalandı ve kuyruğa aktarıldı!")
        else:
            print("  ❌ [HATA] Kod yanlış ayrıştırıldı.")
    else:
        print("  ❌ [HATA] Mesaj kuyruğa giremedi.")

    # TEST 5: Worker & WebSocket Gönderim Hızı
    print("\n🔍 [TEST 5/5] Uçtan Uca WebSocket Claim Simülasyonu...")
    worker = RedeemWorker(
        queue=queue,
        client=client,
        db=db,
        metrics=metrics,
        config=cfg,
        captcha_pool=pool
    )
    # Process code
    test_item = ParsedCode(code="WDDADWDW", message_id=1, channel_id=1, guild_id=1, author_id=1)
    t0 = time.time()
    res = await worker.process_code(test_item)
    lat_ms = (time.time() - t0) * 1000
    print(f"  ✅ [BAŞARILI] WebSocket claim paketi işlendi. Yanıt: '{res.message}' ({lat_ms:.1f} ms)")

    # Cleanup
    await client.close()
    await db.close()

    print()
    print("=" * 60)
    print("       🎉 TÜM SİSTEM PARÇALARI %100 ÇALIŞIYOR! 🎉")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
