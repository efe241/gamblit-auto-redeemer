"""
Background worker that consumes codes from queue and orchestrates redemption.
Handles retry policy, rate-limit backoffs, latency recording, and DB synchronization.
"""
import asyncio
import logging
import time
from typing import Optional, Any
from app.models import ParsedCode, RedeemStatus, RedeemResult, RedeemLatency
from app.queue import RedeemQueue
from app.gamblit_client import GamblitClient
from app.database import Database
from app.metrics import MetricsTracker
from app.config import Config

log = logging.getLogger("gamblit_redeemer.worker")


class RedeemWorker:
    def __init__(
        self,
        queue: RedeemQueue,
        client: GamblitClient,
        db: Database,
        metrics: MetricsTracker,
        config: Config,
        captcha_pool: Optional[Any] = None,
        account_manager: Optional[Any] = None,
    ):
        self.queue = queue
        self.client = client
        self.db = db
        self.metrics = metrics
        self.config = config
        self.captcha_pool = captcha_pool
        self.account_manager = account_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Starts worker loop in background."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="RedeemWorkerLoop")
        log.info("RedeemWorker started.")

    async def stop(self):
        """Gracefully stops the worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        log.info("RedeemWorker stopped.")

    async def _run_loop(self):
        """Main processing loop."""
        while self._running:
            try:
                parsed_item = await self.queue.dequeue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Worker queue read error: {e}", exc_info=True)
                await asyncio.sleep(0.5)
                continue

            try:
                await self.process_code(parsed_item)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error processing code '{parsed_item.code}': {e}", exc_info=True)
            finally:
                self.queue.task_done()

    async def process_code(self, item: ParsedCode) -> RedeemResult:
        """Processes single code or multi-level drop across accounts."""
        latency = RedeemLatency(
            t0_discord_received=item.received_at,
            t1_parsed=item.parsed_at,
            t2_request_started=0.0,
            t3_response_received=0.0,
        )

        # 1. Multi-level Drop Mode (All accounts parallel, highest to lowest reward)
        if item.level_codes:
            log.info(f"===> [DROP BAŞLADI] {len(item.level_codes)} kodlu drop işleniyor (Tüm hesaplar paralel)...")
            multi_results = []
            if self.account_manager and len(self.account_manager.accounts) > 0:
                multi_results = await self.account_manager.redeem_drop(
                    item.level_codes, captcha_pool=self.captcha_pool
                )
            else:
                user_lvl = self.client._profile.level if self.client._profile else 1
                eligible = [(lvl, c) for lvl, c in item.level_codes if user_lvl >= lvl]
                for req_lvl, c in eligible:
                    r = await self.client.redeem_code(c, latency=latency)
                    multi_results.append({"code": c, "req_level": req_lvl, "result": r})

            # Record stats & update DB for each code
            best_result = None
            for res_item in multi_results:
                r = res_item.get("result")
                if r:
                    self.metrics.record_redeem(r)
                    await self.db.update_redeem_result(r)
                    if r.status == RedeemStatus.SUCCESS and not best_result:
                        best_result = r

            if not best_result and multi_results:
                best_result = multi_results[0].get("result")

            return best_result or RedeemResult(
                code=item.code,
                status=RedeemStatus.SUCCESS,
                message=f"Drop processed ({len(multi_results)} claims evaluated)",
            )

        # 2. Single Code Mode
        code = item.code
        log.info(f"===> [Redeem Start] Processing code: {code}")
        await self.db.mark_processing(code)

        attempt = 1
        result: Optional[RedeemResult] = None

        captcha_token = ""
        if self.captcha_pool:
            captcha_token = await self.captcha_pool.get_token()

        while attempt <= (self.config.max_retries + 1):
            if self.account_manager and len(self.account_manager.accounts) > 0:
                multi_results = await self.account_manager.redeem_all(
                    code, req_level=item.required_level, captcha_token=captcha_token
                )
                for res_entry in multi_results:
                    acc_name = res_entry.get("account_name", "Hesap")
                    r = res_entry.get("result")
                    if r:
                        log.info(f"👥 [{acc_name}] Kod: {code} -> {r.status.value} ({r.message}) | {r.latency.http_request_ms:.1f}ms")
                        if r.status == RedeemStatus.SUCCESS:
                            result = r
                if not result and multi_results:
                    result = multi_results[0].get("result")
                if not result:
                    result = await self.client.redeem_code(
                        code, latency=latency, attempt=attempt, captcha_token=captcha_token
                    )
            else:
                result = await self.client.redeem_code(
                    code,
                    latency=latency,
                    attempt=attempt,
                    captcha_token=captcha_token,
                )

            # Check if retry is needed
            if result.status.is_terminal:
                break

            # Auto-detect captcha error: invalid or missing captcha
            is_captcha_err = (
                "CAPTCHA" in result.message.upper()
                or (result.response_data and "CAPTCHA" in str(result.response_data).upper())
            )
            if is_captcha_err and attempt <= self.config.max_retries:
                log.warning(f"🛡️ Captcha engeli tespit edildi! ({result.message}). Otomatik çözüm deneniyor...")
                if self.captcha_pool:
                    self.captcha_pool.invalidate()
                    fresh_token = await self.captcha_pool.auto_solve_once()
                    if fresh_token:
                        captcha_token = fresh_token
                        log.info(f"⚡ Yeni hCaptcha tokenı alındı, kod tekrar deneniyor (#{attempt+1})...")
                        attempt += 1
                        continue

            if result.status == RedeemStatus.RATE_LIMITED and attempt <= self.config.max_retries:
                wait_sec = (
                    result.retry_after
                    if result.retry_after
                    else (self.config.rate_limit_backoff_factor ** attempt)
                )
                log.warning(f"Rate limited on code '{code}'. Waiting {wait_sec:.2f}s before retry #{attempt+1}")
                await asyncio.sleep(wait_sec)
                attempt += 1
                continue

            if result.status.is_retryable and attempt <= self.config.max_retries:
                backoff = self.config.rate_limit_backoff_factor * attempt
                log.warning(f"Retryable error ({result.status.value}) for code '{code}'. Backoff {backoff:.2f}s")
                await asyncio.sleep(backoff)
                attempt += 1
                continue

            break

        # Record metrics and log
        self.metrics.record_redeem(result)
        await self.db.update_redeem_result(result)

        latency_breakdown = self.metrics.format_latency_breakdown(result.latency)
        if result.success:
            log.info(f"[SUCCESS] Code: {code} | {result.message} | {latency_breakdown}")
        else:
            log.warning(f"[{result.status.value}] Code: {code} | {result.message} | {latency_breakdown}")

        return result
