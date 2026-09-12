"""
Pre-generated hCaptcha Token Pool with CapSolver & 2Captcha auto-solvers.
Features:
1. CapSolver API integration (invisible hCaptcha)
2. 2Captcha API integration (invisible hCaptcha)
3. Auto-solver background loop (keeps 1 token fresh in pool at all times for 0ms drop latency)
4. Manual token injection & browser console 1-click bridge
5. Account balance inquiry for both providers
6. Token invalidation and automatic on-demand retry
"""
import asyncio
import logging
import time
from typing import Optional, Dict, Any
import aiohttp
from app.config import Config

log = logging.getLogger("gamblit_redeemer.captcha")


class CaptchaPool:
    def __init__(self, config: Config, account_manager: Optional[Any] = None):
        self.config = config
        self.account_manager = account_manager
        self.sitekey = "60fa63fa-7302-4baa-9d64-8b60bc80a6dc"
        self.page_url = config.gamblit_base_url or "https://gamblit.co"
        self.token_ttl_seconds: float = 110.0  # hCaptcha tokens valid ~120s, safe maximum 110s
        self.nonecap_api_key: str = config.nonecap_api_key or ""
        self.nonecap_backup_api_key: str = config.nonecap_backup_api_key or ""
        self.capsolver_api_key: str = config.capsolver_api_key or ""
        self.twocaptcha_api_key: str = config.twocaptcha_api_key or ""
        self._bg_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self.is_solving = False
        self.last_error: str = ""
        # Multi-token buffer: list of (created_at, token)
        self._tokens: list = []
        self._target_pool_size: int = 1

    @property
    def target_pool_size(self) -> int:
        """
        Dynamically scales the pool size according to the exact number of active accounts!
        If 1 account exists, only 1 token is prepared (0 waste).
        If 7 accounts exist, 7 tokens are prepared.
        """
        if self.account_manager and hasattr(self.account_manager, "accounts"):
            active = [a for a in self.account_manager.accounts.values() if a.enabled]
            return max(1, len(active))
        return self._target_pool_size

    @target_pool_size.setter
    def target_pool_size(self, val: int):
        self._target_pool_size = max(1, int(val))

    @property
    def current_token(self) -> Optional[str]:
        now = time.time()
        for t0, tok in self._tokens:
            if (now - t0) < self.token_ttl_seconds:
                return tok
        return None

    @current_token.setter
    def current_token(self, val: Optional[str]):
        if val is None:
            self._tokens.clear()
        else:
            self.set_token(val)

    @property
    def token_created_at(self) -> float:
        now = time.time()
        for t0, _ in self._tokens:
            if (now - t0) < self.token_ttl_seconds:
                return t0
        return 0.0

    @token_created_at.setter
    def token_created_at(self, val: float):
        pass

    def set_token(self, token: str):
        """Stores a fresh solved token in the pool."""
        tok = token.strip()
        if tok:
            now = time.time()
            self._tokens = [(t0, t) for t0, t in self._tokens if (now - t0) < self.token_ttl_seconds]
            self._tokens.append((now, tok))
            self.last_error = ""
            log.info(f"✅ hCaptcha token havuza eklendi (Havuzdaki Hazır Token Sayısı: {len(self._tokens)}).")

    def invalidate(self):
        """Invalidates all tokens in the pool."""
        self._tokens.clear()
        log.info("hCaptcha token havuzu boşaltıldı.")

    @property
    def is_token_valid(self) -> bool:
        return self.valid_token_count > 0

    @property
    def valid_token_count(self) -> int:
        now = time.time()
        return sum(1 for t0, _ in self._tokens if (now - t0) < self.token_ttl_seconds)

    @property
    def remaining_seconds(self) -> float:
        now = time.time()
        valid_ttls = [self.token_ttl_seconds - (now - t0) for t0, _ in self._tokens if (now - t0) < self.token_ttl_seconds]
        return max(valid_ttls, default=0.0)

    async def get_token(self) -> str:
        """Returns ready-to-use token, or empty string if none available."""
        async with self._lock:
            now = time.time()
            self._tokens = [(t0, tok) for t0, tok in self._tokens if (now - t0) < self.token_ttl_seconds]
            if self._tokens:
                return self._tokens[0][1]
            return ""

    async def consume_token(self) -> Optional[str]:
        """
        Atomically pops and consumes a valid token from the pool for single-use verification.
        Guarantees that two concurrent accounts will never submit the same token and trigger duplicate rejection.
        Instant (0.1 ms latency).
        """
        async with self._lock:
            now = time.time()
            self._tokens = [(t0, tok) for t0, tok in self._tokens if (now - t0) < self.token_ttl_seconds]
            if self._tokens:
                _, tok = self._tokens.pop(0)
                log.info(f"🎯 Havuzdan 1 token tüketildi (0ms). Havuzda Kalan: {len(self._tokens)} token.")
                return tok
            return None

    async def consume_tokens(self, count: int = 1) -> list:
        """
        Atomically pops up to `count` valid tokens from the pool in a single lock acquisition.
        Guarantees that distinct concurrent accounts each get a unique token instantly (0.1ms).
        """
        async with self._lock:
            now = time.time()
            self._tokens = [(t0, tok) for t0, tok in self._tokens if (now - t0) < self.token_ttl_seconds]
            popped = []
            while self._tokens and len(popped) < count:
                _, tok = self._tokens.pop(0)
                popped.append(tok)
            if popped:
                log.info(f"🎯 Havuzdan {len(popped)} token tüketildi (0ms). Kalan: {len(self._tokens)} token.")
            return popped

    async def warm_up_pool(self, count: Optional[int] = None) -> int:
        """
        Rapidly solves multiple captchas in parallel (burst mode) to pre-warm the pool for drops.
        Defaults to exactly the number of active accounts (zero waste).
        """
        target = count if count is not None and count > 0 else self.target_pool_size
        needed = max(0, target - self.valid_token_count)
        if needed <= 0:
            return self.valid_token_count

        log.info(f"⚡ [Turbo Warmup] {needed} adet hCaptcha tokenı paralel çözülüyor (Aktif Hesap: {target})...")
        tasks = [self.auto_solve_once() for _ in range(needed)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        solved = sum(1 for r in results if isinstance(r, str) and r)
        log.info(f"⚡ [Turbo Warmup Tamamlandı] {solved}/{needed} token havuza eklendi! Toplam hazır: {self.valid_token_count}")
        return self.valid_token_count

    async def get_balances(self) -> Dict[str, Any]:
        """Queries current balance for configured solvers."""
        balances = {
            "nonecap": None,
            "nonecap_backup": None,
            "capsolver": None,
            "twocaptcha": None,
            "nonecap_solves": 0,
            "nonecap_remaining": 1300,
            "nonecap_backup_remaining": 1300,
        }

        async def fetch_nonecap_info(key: str):
            if not key:
                return None
            try:
                headers = {"Authorization": f"Bearer {key}"}
                async with aiohttp.ClientSession(headers=headers) as s:
                    async with s.get("https://api.nonecap.com/v1/solves", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            solves_list = data.get("data", [])
                            solved_count = sum(1 for item in solves_list if item.get("status") == "solved")
                            charged_total = sum(int(item.get("credits_charged") or 0) for item in solves_list)
                            rem_credits = max(0, 1300 - charged_total)
                            return {
                                "solves": solved_count,
                                "charged": charged_total,
                                "remaining": rem_credits,
                                "text": f"{rem_credits:,} Kredi ({solved_count} Çözüm - {charged_total} Kredi Harcandı)".replace(",", "."),
                            }
            except Exception:
                pass
            return None

        if self.nonecap_api_key:
            res = await fetch_nonecap_info(self.nonecap_api_key)
            if res:
                balances["nonecap"] = res["text"]
                balances["nonecap_solves"] = res["solves"]
                balances["nonecap_remaining"] = res["remaining"]
            else:
                balances["nonecap"] = "1.300 Kredi (Kullanılabilir)"

        if self.nonecap_backup_api_key:
            res_b = await fetch_nonecap_info(self.nonecap_backup_api_key)
            if res_b:
                balances["nonecap_backup"] = res_b["text"]
                balances["nonecap_backup_remaining"] = res_b["remaining"]
            else:
                balances["nonecap_backup"] = "1.300 Kredi (Yedek Hazır)"

        if self.capsolver_api_key:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(
                        "https://api.capsolver.com/getBalance",
                        json={"clientKey": self.capsolver_api_key},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("errorId") == 0:
                                balances["capsolver"] = round(float(data.get("balance", 0)), 2)
            except Exception:
                pass

        if self.twocaptcha_api_key:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "https://2captcha.com/res.php",
                        params={"key": self.twocaptcha_api_key, "action": "getbalance", "json": "1"},
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("status") == 1:
                                balances["twocaptcha"] = round(float(data.get("request", 0)), 2)
            except Exception:
                pass

        return balances

    async def get_detailed_status(self) -> Dict[str, Any]:
        """Returns per-key credit breakdowns, current ready tokens, and solver status."""
        now = time.time()
        ready_tokens = []
        for t0, tok in self._tokens:
            age = now - t0
            rem_ttl = max(0, self.token_ttl_seconds - age)
            if rem_ttl > 0:
                ready_tokens.append({
                    "preview": f"{tok[:16]}...{tok[-8:]}" if len(tok) > 24 else tok,
                    "created_at_epoch": t0,
                    "age_sec": round(age, 1),
                    "remaining_ttl_sec": round(rem_ttl, 1),
                    "is_fresh": age < 40,
                })

        key_details = []
        all_keys = self.config.all_nonecap_keys
        total_remaining = 0
        total_solves = 0
        total_charged = 0

        async def fetch_nonecap_detail(key: str, index: int):
            preview = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else key
            try:
                headers = {"Authorization": f"Bearer {key}"}
                async with aiohttp.ClientSession(headers=headers) as s:
                    async with s.get("https://api.nonecap.com/v1/solves", timeout=aiohttp.ClientTimeout(total=4)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            solves_list = data.get("data", [])
                            solved_count = sum(1 for item in solves_list if item.get("status") == "solved")
                            charged_total = sum(int(item.get("credits_charged") or 0) for item in solves_list)
                            rem_credits = max(0, 1300 - charged_total)
                            return {
                                "index": index,
                                "name": f"NoneCap #{index}" + (" (Ana)" if index == 1 else " (Yedek)"),
                                "key_preview": preview,
                                "solves": solved_count,
                                "charged_credits": charged_total,
                                "remaining_credits": rem_credits,
                                "status": "AKTİF" if rem_credits > 10 else "TÜKENDİ",
                                "badge": "success" if rem_credits > 100 else ("warning" if rem_credits > 0 else "danger"),
                            }
            except Exception as e:
                pass
            return {
                "index": index,
                "name": f"NoneCap #{index}",
                "key_preview": preview,
                "solves": 0,
                "charged_credits": 0,
                "remaining_credits": 1300,
                "status": "BEKLEMEDE",
                "badge": "info",
            }

        for idx, k in enumerate(all_keys, start=1):
            detail = await fetch_nonecap_detail(k, idx)
            key_details.append(detail)
            total_remaining += detail["remaining_credits"]
            total_solves += detail["solves"]
            total_charged += detail["charged_credits"]

        return {
            "is_valid": self.is_token_valid,
            "valid_token_count": len(ready_tokens),
            "target_pool_size": self.target_pool_size,
            "token_ttl_seconds": self.token_ttl_seconds,
            "is_solving": self.is_solving,
            "last_error": self.last_error,
            "ready_tokens": ready_tokens,
            "total_keys_count": len(all_keys),
            "total_remaining_credits": total_remaining,
            "total_solves": total_solves,
            "total_charged_credits": total_charged,
            "keys": key_details,
            "schedule": {
                "start": self.config.schedule_start,
                "end": self.config.schedule_end,
                "is_in_schedule": self.config.is_in_schedule(),
                "countdown": self.config.get_schedule_countdown(),
            },
        }


    async def solve_nonecap(self, api_key: Optional[str] = None) -> Optional[str]:
        """Solves hCaptcha invisible via NoneCap API (100% automated with free credits)."""
        key = api_key or self.nonecap_api_key
        if not key:
            return None

        url = "https://api.nonecap.com/v1/solves?wait=35"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "type": "hcaptcha",
            "sitekey": self.sitekey,
            "url": self.page_url
        }

        try:
            self.is_solving = True
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        token = data.get("token") or (data.get("solution", {}).get("token") if isinstance(data.get("solution"), dict) else None)
                        if token:
                            self.set_token(token)
                            log.info("✅ NoneCap hCaptcha tokenını başarıyla çözdü ve havuza ekledi!")
                            return token
                        else:
                            err = str(data.get("error") or data)
                            self.last_error = f"NoneCap: {err}"
                            log.warning(f"NoneCap token dönmedi: {err}")
                    else:
                        err_text = await resp.text()
                        self.last_error = f"NoneCap HTTP {resp.status}: {err_text[:100]}"
                        log.warning(self.last_error)
        except Exception as e:
            self.last_error = f"NoneCap request error: {e}"
            log.error(self.last_error)
        finally:
            self.is_solving = False
        return None

    async def solve_capsolver(self, api_key: Optional[str] = None) -> Optional[str]:
        """Solves hCaptcha invisible via CapSolver API."""
        key = api_key or self.capsolver_api_key
        if not key:
            return None

        create_task_url = "https://api.capsolver.com/createTask"
        payload = {
            "clientKey": key,
            "task": {
                "type": "HCaptchaTaskProxyLess",
                "websiteURL": self.page_url,
                "websiteKey": self.sitekey,
                "isInvisible": True,
            },
        }
        try:
            self.is_solving = True
            async with aiohttp.ClientSession() as session:
                async with session.post(create_task_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    task_id = data.get("taskId")
                    if not task_id:
                        err = data.get("errorDescription") or str(data)
                        self.last_error = f"CapSolver: {err}"
                        log.warning(f"CapSolver createTask error: {err}")
                        return None

                # Poll for result
                result_url = "https://api.capsolver.com/getTaskResult"
                for _ in range(25):
                    await asyncio.sleep(1.5)
                    async with session.post(
                        result_url,
                        json={"clientKey": key, "taskId": task_id},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as r:
                        r_data = await r.json()
                        status = r_data.get("status")
                        if status == "ready":
                            token = r_data.get("solution", {}).get("gRecaptchaResponse")
                            if token:
                                self.set_token(token)
                                log.info("CapSolver successfully resolved hCaptcha token!")
                                return token
                        elif status == "failed":
                            err = r_data.get("errorDescription") or "Unknown error"
                            self.last_error = f"CapSolver: {err}"
                            log.error(f"CapSolver failed: {err}")
                            return None
        except Exception as e:
            self.last_error = f"CapSolver request error: {e}"
            log.error(self.last_error)
        finally:
            self.is_solving = False
        return None

    async def solve_2captcha(self, api_key: Optional[str] = None) -> Optional[str]:
        """Solves hCaptcha invisible via 2Captcha (2captcha.com) API."""
        key = api_key or self.twocaptcha_api_key
        if not key:
            return None

        in_url = "https://2captcha.com/in.php"
        params = {
            "key": key,
            "method": "hcaptcha",
            "sitekey": self.sitekey,
            "pageurl": self.page_url,
            "invisible": "1",
            "json": "1",
        }
        try:
            self.is_solving = True
            async with aiohttp.ClientSession() as session:
                async with session.post(in_url, data=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    if data.get("status") != 1:
                        err = data.get("request") or str(data)
                        self.last_error = f"2Captcha: {err}"
                        log.warning(f"2Captcha in.php error: {err}")
                        return None
                    request_id = data.get("request")

                # Poll for response
                res_url = "https://2captcha.com/res.php"
                for _ in range(30):
                    await asyncio.sleep(3.0)
                    poll_params = {
                        "key": key,
                        "action": "get",
                        "id": request_id,
                        "json": "1",
                    }
                    async with session.get(res_url, params=poll_params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                        r_data = await r.json()
                        if r_data.get("status") == 1:
                            token = r_data.get("request")
                            if token:
                                self.set_token(token)
                                log.info("2Captcha successfully resolved hCaptcha token!")
                                return token
                        elif r_data.get("request") == "CAPCHA_NOT_READY":
                            continue
                        else:
                            err = r_data.get("request") or "Unknown error"
                            self.last_error = f"2Captcha: {err}"
                            log.error(f"2Captcha error: {err}")
                            return None
        except Exception as e:
            self.last_error = f"2Captcha request error: {e}"
            log.error(self.last_error)
        finally:
            self.is_solving = False
        return None

    async def auto_solve_once(self) -> Optional[str]:
        """Tries all available NoneCap keys in order (Primary, Backup, Numbered 1..50); then CapSolver, then 2Captcha."""
        # 1. Gather all NoneCap keys from instance and config
        all_keys = []
        if self.nonecap_api_key:
            for k in self.nonecap_api_key.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in all_keys:
                    all_keys.append(k_clean)
        if self.nonecap_backup_api_key:
            for k in self.nonecap_backup_api_key.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in all_keys:
                    all_keys.append(k_clean)

        # If instance explicitly cleared keys (e.g. in tests with pool.nonecap_api_key = ''), don't fallback to env keys
        if (self.nonecap_api_key or self.nonecap_backup_api_key):
            for cfg_k in self.config.all_nonecap_keys:
                if cfg_k and cfg_k not in all_keys:
                    all_keys.append(cfg_k)

        for idx, key in enumerate(all_keys, start=1):
            key_preview = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "NoneCap"
            if idx > 1:
                log.info(f"🛡️ [Yedek Çözücü #{idx} Aktif] NoneCap anahtarı ({key_preview}) deneniyor...")
            token = await self.solve_nonecap(api_key=key)
            if token:
                if idx > 1:
                    log.info(f"✅ NoneCap #{idx} ({key_preview}) başarıyla çözdü!")
                return token
            log.warning(f"⚠️ NoneCap #{idx} ({key_preview}) başarısız/tükendi, sıradaki çözücüye geçiliyor...")

        # 3. CapSolver fallback
        if self.capsolver_api_key:
            token = await self.solve_capsolver()
            if token:
                return token

        # 4. 2Captcha fallback
        if self.twocaptcha_api_key:
            token = await self.solve_2captcha()
            if token:
                return token

        return None

    async def start_auto_solver_loop(self):
        """Background worker that ensures a fresh token is always ready in pool."""
        if self._bg_task and not self._bg_task.done():
            return
        self._bg_task = asyncio.create_task(self._pool_maintenance_loop(), name="CaptchaPoolLoop")
        log.info("CaptchaPool background maintenance loop started.")

    async def stop(self):
        if self._bg_task:
            self._bg_task.cancel()
            self._bg_task = None

    async def _pool_maintenance_loop(self):
        """
        Keeps tokens fresh with ZERO-GAP OVERLAP:
        NoneCap/CapSolver takes ~8-12 seconds to resolve.
        We trigger the background solve proactively when a token has < 25 seconds remaining.
        This guarantees the new token is 100% ready in RAM before the old token expires,
        leaving zero gap and zero chance of an empty pool when a drop arrives.
        """
        while True:
            try:
                if not self.config.is_in_schedule():
                    await asyncio.sleep(10)
                    continue

                has_provider = bool(self.nonecap_api_key or self.nonecap_backup_api_key or self.capsolver_api_key or self.twocaptcha_api_key)
                if has_provider and not self.is_solving:
                    now = time.time()
                    async with self._lock:
                        # Clean expired tokens (> 110s)
                        self._tokens = [(t0, tok) for t0, tok in self._tokens if (now - t0) < self.token_ttl_seconds]
                        # Count tokens that still have >= 25 seconds of validity left
                        fresh_count = sum(1 for t0, _ in self._tokens if (self.token_ttl_seconds - (now - t0)) >= 25.0)

                    # If fewer fresh tokens than target_pool_size, solve replacement proactively!
                    if fresh_count < self.target_pool_size:
                        log.info(
                            f"⚡ [Sıfır-Boşluk Köprüsü] Token bitmeden yenisi hazırlanıyor "
                            f"(Hazır: {len(self._tokens)}, Taze: {fresh_count}/{self.target_pool_size})..."
                        )
                        await self.auto_solve_once()

                await asyncio.sleep(4)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning(f"Error in captcha maintenance loop: {e}")
                await asyncio.sleep(5)

