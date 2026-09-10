"""
Main application entry point for Gamblit Promo Code Auto-Redeemer.
Coordinates DiscordListener, RedeemWorker, Database, and HealthMonitor.
"""
import asyncio
import signal
import sys
import argparse

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from app.config import cfg
from app.logging_config import setup_logger
from app.database import Database
from app.metrics import MetricsTracker
from app.gamblit_client import GamblitClient
from app.queue import RedeemQueue
from app.worker import RedeemWorker
from app.health import HealthMonitor
from app.discord_listener import DiscordCodeListener, register_listener_commands


async def run_app():
    parser = argparse.ArgumentParser(description="Gamblit Promo Code Auto-Redeemer")
    parser.add_argument("--test-auth", action="store_true", help="Test Gamblit cookies/session and exit")
    parser.add_argument("--check-db", action="store_true", help="Inspect database status and exit")
    parser.add_argument("--redeem", type=str, default="", help="Redeem a specific promo code directly on Gamblit and exit")
    args = parser.parse_args()

    # 1. Initialize Logger
    logger = setup_logger(
        name="gamblit_redeemer",
        log_level=cfg.log_level,
        log_file=cfg.log_file,
    )
    logger.info("Starting Gamblit Promo Code Auto-Redeemer...")

    # 2. Initialize Database
    db = Database(db_path=cfg.database_path)
    await db.connect()
    logger.info(f"Database initialized at: {cfg.database_path}")

    if args.check_db:
        stats = await db.get_stats()
        logger.info(f"Database statistics: {stats}")
        await db.close()
        return

    # 3. Initialize Gamblit HTTP Client
    client = GamblitClient(config=cfg)

    # 4. Auth Test Mode
    if args.test_auth:
        logger.info("Running Gamblit session authentication test...")
        profile = await client.get_profile()
        if profile.is_authenticated:
            logger.info(
                f"[SUCCESS] Gamblit session is VALID! Logged in as: '{profile.username}' "
                f"(Level: {profile.level}, Balance: {profile.balance_dl} DL)"
            )
        else:
            logger.error(
                "[FAILED] Gamblit session is INVALID or unauthenticated. "
                "Check GAMBLIT_COOKIES in .env and make sure cf_clearance is valid."
            )
        await client.close()
        await db.close()
        return

    # 4.1 Manual Redeem Mode
    if args.redeem:
        target_code = args.redeem.strip().upper()
        logger.info(f"Manually testing redeem for code: '{target_code}'...")
        profile = await client.get_profile()
        if not profile.is_authenticated:
            logger.error("Cannot redeem: Gamblit session is unauthenticated.")
            await client.close()
            await db.close()
            return

        import time
        from app.models import RedeemLatency
        latency = RedeemLatency(t0_discord_received=time.time())
        result = await client.redeem_code(target_code, latency=latency)

        logger.info(f"Redeem Status : {result.status.value}")
        logger.info(f"Server Message: {result.message}")
        logger.info(f"Raw Response  : {result.response_data}")
        logger.info(f"Latency       : {result.latency.http_request_ms:.2f} ms")

        await db.update_redeem_result(result)
        await client.close()
        await db.close()
        return

    # 5. Cold-Start Warmup: Pre-warm Gamblit HTTP session (DNS + SSL + TCP pool)
    try:
        await client.get_session()
        logger.info("Gamblit HTTP session pool warmed up.")
        asyncio.create_task(client.connect_ws())
    except Exception as e:
        logger.warning(f"Session warmup error: {e}")

    # 5.1 Initialize Multi-Account Manager
    from app.account_manager import AccountManager
    account_manager = AccountManager(config=cfg)
    await account_manager.start_all()

    # 6. Initialize Captcha Pool, Queue & Worker
    from app.captcha_pool import CaptchaPool
    from app.web_panel import WebPanel

    captcha_pool = CaptchaPool(config=cfg)
    captcha_pool.nonecap_api_key = cfg.nonecap_api_key
    captcha_pool.capsolver_api_key = cfg.capsolver_api_key
    captcha_pool.twocaptcha_api_key = cfg.twocaptcha_api_key
    if captcha_pool.nonecap_api_key or cfg.capsolver_api_key or cfg.twocaptcha_api_key:
        await captcha_pool.start_auto_solver_loop()

    queue = RedeemQueue(db=db)
    await queue.initialize()

    metrics = MetricsTracker()
    worker = RedeemWorker(
        queue=queue,
        client=client,
        db=db,
        metrics=metrics,
        config=cfg,
        captcha_pool=captcha_pool,
        account_manager=account_manager,
    )
    await worker.start()

    # 7. Initialize Health Watchdog
    health = HealthMonitor(client=client, db=db, interval_sec=120.0)
    await health.start()

    # 8. Initialize Discord Gateway Listener (Supports User Account Tokens & Bot Tokens)
    from app.gateway_listener import DiscordGatewayListener
    gateway_listener = DiscordGatewayListener(
        config=cfg,
        queue=queue,
        metrics=metrics,
        db=db,
        client=client,
    )

    # 9. Initialize Web Panel Dashboard
    web_panel = WebPanel(
        config=cfg,
        client=client,
        db=db,
        metrics=metrics,
        queue=queue,
        captcha_pool=captcha_pool,
        gateway_listener=gateway_listener,
        account_manager=account_manager,
        port=cfg.port,
    )
    await web_panel.start()

    # 9.1 Initialize Live Console Dashboard
    from app.console_dashboard import ConsoleDashboard
    console_dash = ConsoleDashboard(
        config=cfg,
        client=client,
        captcha_pool=captcha_pool,
        metrics=metrics,
        queue=queue,
        db=db,
        gateway_listener=gateway_listener,
        account_manager=account_manager,
        interval_sec=3.0,
    )
    await console_dash.start()

    # Start Discord Gateway Listener if token configured
    if cfg.discord_token:
        await gateway_listener.start()

    # Graceful Shutdown Handling
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Signal handling on Windows
            pass

    # Check configuration readiness
    validation_errors = cfg.validate_for_production()
    if validation_errors:
        for err in validation_errors:
            logger.warning(f"[Config Warning] {err}")
        logger.info("Running in development/monitoring mode. Set missing .env items for full production.")

    try:
        # Wait until shutdown requested
        while not shutdown_event.is_set():
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Keyboard interrupt received.")
    finally:
        logger.info("Cleaning up resources...")
        await gateway_listener.stop()
        await console_dash.stop()
        await web_panel.stop()
        await health.stop()
        await worker.stop()
        await account_manager.close_all()
        await client.close()
        await db.close()
        logger.info("All services shut down cleanly. Bye!")


def main():
    try:
        asyncio.run(run_app())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
