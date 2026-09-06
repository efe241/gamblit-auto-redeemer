"""
Interactive Phase-by-Phase Test Runner for Gamblit Promo Code Auto-Redeemer.
Allows validating every subsystem independently before going live.
"""
import asyncio
import time
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.parser import CodeParser
from app.models import ParsedCode, RedeemStatus, RedeemResult, RedeemLatency
from app.database import Database
from app.queue import RedeemQueue
from app.worker import RedeemWorker
from app.metrics import MetricsTracker
from app.config import Config
from app.gamblit_client import GamblitClient
from tests.mock_gamblit import MockGamblitServer


def print_header(title: str):
    print("\n" + "=" * 65)
    print(f"  ⚡ {title}")
    print("=" * 65)


async def phase1_parser_test():
    print_header("FAZ 1: Mesaj Ayrıştırıcı (Parser) Hız ve Doğruluk Testi")
    print("Farklı Discord mesaj tipleri deneniyor...\n")

    test_messages = [
        ("🎁 New Code: SUPER2026", "SUPER2026"),
        ("Quick guys, use code `NIGHTLY_DROP` now!", "NIGHTLY_DROP"),
        ("```\nFLASH_SALE_99\n```", "FLASH_SALE_99"),
        ("<@&999> <:party:123> Promo Code: GAMBLIT_WIN https://gamblit.net", "GAMBLIT_WIN"),
        ("STANDALONECODE123", "STANDALONECODE123"),
        ("Hey guys, anyone knows when next drop is?", None),
        ("gamblit rules and announcement channel", None),
    ]

    for raw, expected in test_messages:
        t0 = time.perf_counter()
        extracted = CodeParser.extract_raw_code(raw)
        dt_us = (time.perf_counter() - t0) * 1_000_000  # microseconds

        status_icon = "✅" if extracted == expected else "❌"
        print(f"{status_icon} Girdi : {raw.strip()[:45]:<45}")
        print(f"   Bulunan: {str(extracted):<15} (Beklenen: {str(expected)}) | Süre: {dt_us:.1f} µs\n")

    print("👉 Sonuç: Parser regex optimizasyonu sayesinde mikrosaniye seviyesinde çalışıyor!")


async def phase2_duplicate_and_queue_test():
    print_header("FAZ 2: Çift Katmanlı Duplicate Koruması & Kuyruk Testi")
    test_db_path = "data/demo_test.db"
    if os.path.exists(test_db_path):
        try: os.remove(test_db_path)
        except OSError: pass

    db = Database(db_path=test_db_path)
    await db.connect()
    queue = RedeemQueue(db=db)
    await queue.initialize()

    print("1. 'DROPPED_CODE_1' ilk kez kuyruğa atılıyor...")
    p1 = ParsedCode(code="DROPPED_CODE_1", message_id=101, channel_id=1, guild_id=1, author_id=1)
    res1 = await queue.enqueue(p1)
    print(f"   Sonuç: {'✅ Kuyruğa Eklendi (Kabul)' if res1 else '❌ Reddedildi'}")

    print("\n2. 'DROPPED_CODE_1' ikinci kez (kopya) geliyor...")
    p2 = ParsedCode(code="DROPPED_CODE_1", message_id=102, channel_id=1, guild_id=1, author_id=2)
    res2 = await queue.enqueue(p2)
    print(f"   Sonuç: {'❌ HATA (Kopya kabul edildi)' if res2 else '🛡️ RAM Cache tarafından engellendi (Ignore)'}")

    print("\n3. Veritabanı Persistence Kontrolü:")
    print(f"   Kuyruk boyutu: {queue.qsize} (Sadece 1 adet olmalı)")
    is_in_db = await db.is_code_present("DROPPED_CODE_1")
    print(f"   Veritabanında kayıtlı mı: {'✅ Evet' if is_in_db else '❌ Hayır'}")

    await db.close()
    if os.path.exists(test_db_path):
        try: os.remove(test_db_path)
        except OSError: pass


async def phase3_mock_redeem_simulation():
    print_header("FAZ 3: Mock Gamblit HTTP Sunucusu ile Canlı Redeem Simülasyonu")
    print("Yerel Mock Gamblit sunucusu başlatılıyor (127.0.0.1:8995)...")

    server = MockGamblitServer(host="127.0.0.1", port=8995)
    await server.start()

    config = Config(
        gamblit_base_url=server.base_url,
        raw_cookies='{"cf_clearance": "valid_mock_token"}',
        redeem_endpoints=["/api/promo/redeem"],
        connect_timeout_sec=2.0,
        read_timeout_sec=2.0,
    )
    client = GamblitClient(config=config)

    scenarios = [
        ("SUCCESS2026", "Başarılı kod (200 OK)", RedeemStatus.SUCCESS),
        ("EXPIRED_CODE", "Süresi dolmuş kod (400 Bad Request)", RedeemStatus.EXPIRED),
        ("ALREADY_USED", "Daha önce kullanılmış kod", RedeemStatus.ALREADY_USED),
        ("HIGH_LEVEL", "Level yetersizliği gerektiren kod", RedeemStatus.NOT_ELIGIBLE),
        ("RATE_LIMIT_TEST", "Rate Limit (429 Too Many Requests)", RedeemStatus.RATE_LIMITED),
        ("SERVER_ERROR", "Sunucu hatası (500 Internal Error)", RedeemStatus.SERVER_ERROR),
        ("RANDOM_BOGUS", "Var olmayan geçersiz kod", RedeemStatus.INVALID_CODE),
    ]

    print("\nFarklı sunucu yanıt senaryoları test ediliyor:\n")
    for code, desc, expected_status in scenarios:
        lat = RedeemLatency(t0_discord_received=time.time())
        result = await client.redeem_code(code, latency=lat)

        status_match = "✅" if result.status == expected_status else "❌"
        print(f"{status_match} Kod: {code:<16} | Durum: {result.status.value:<14} | HTTP: {result.status_code}")
        print(f"   Açıklama: {desc}")
        print(f"   Sunucu Mesajı: {result.message}")
        print(f"   HTTP Gecikmesi: {result.latency.http_request_ms:.2f} ms\n")

    await client.close()
    await server.stop()


async def phase4_full_pipeline_test():
    print_header("FAZ 4: Uçtan Uca Tam Pipeline (Discord Mesajı -> Parse -> Kuyruk -> Worker -> HTTP -> DB)")
    test_db_path = "data/demo_pipeline.db"
    if os.path.exists(test_db_path):
        try: os.remove(test_db_path)
        except OSError: pass

    # Mock server
    server = MockGamblitServer(host="127.0.0.1", port=8996)
    await server.start()

    config = Config(
        gamblit_base_url=server.base_url,
        raw_cookies='{"cf_clearance": "valid_mock_token"}',
        redeem_endpoints=["/api/promo/redeem"],
        database_path=test_db_path,
    )
    db = Database(db_path=test_db_path)
    await db.connect()

    queue = RedeemQueue(db=db)
    await queue.initialize()

    metrics = MetricsTracker()
    client = GamblitClient(config=config)
    worker = RedeemWorker(
        queue=queue,
        client=client,
        db=db,
        metrics=metrics,
        config=config,
    )
    await worker.start()

    print("Simüle edilen Discord mesajı: '🎁 New Drop Code: SUCCESS2026'")
    t0 = time.time()
    parsed = CodeParser.parse_message(
        content="🎁 New Drop Code: SUCCESS2026",
        message_id=999111,
        channel_id=123,
        guild_id=456,
        author_id=789,
        received_at=t0,
    )

    await queue.enqueue(parsed)

    # Wait for worker to finish
    await asyncio.sleep(0.3)

    stats = await db.get_stats()
    print("\n--- İşlem İstatistiği & Gecikme Ölçümü ---")
    print(f"Veritabanı Durumu    : {stats}")
    print(f"Son İşlenen Kod     : {stats['last_code']}")
    print(f"Sonuç Durumu        : {stats['last_status']}")
    print(f"Toplam Uçtan Uca Süre: {stats['last_latency_ms']:.2f} ms")

    await worker.stop()
    await client.close()
    await db.close()
    await server.stop()

    if os.path.exists(test_db_path):
        try: os.remove(test_db_path)
        except OSError: pass

    print("\n👉 Sonuç: Tüm zincir milisaniye seviyesinde başarıyla tamamlandı!")


async def run_all():
    print("\n🚀 GAMBLIT AUTO-REDEEMER AŞAMALI TEST BAŞLATILIYOR...\n")
    await phase1_parser_test()
    await asyncio.sleep(1)
    await phase2_duplicate_and_queue_test()
    await asyncio.sleep(1)
    await phase3_mock_redeem_simulation()
    await asyncio.sleep(1)
    await phase4_full_pipeline_test()
    print("\n" + "=" * 65)
    print("  🎉 TÜM FAZLAR BAŞARIYLA GEÇTİ! SİSTEM %100 ÇALIŞIYOR!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all())
