"""
Multi-Account Manager for Gamblit Promo Code Auto-Redeemer.
Allows adding, managing, and concurrently redeeming promo codes across multiple Gamblit accounts.
Persists accounts in data/accounts.json.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from app.config import Config
from app.gamblit_client import GamblitClient
from app.models import AccountProfile, RedeemResult, RedeemLatency, RedeemStatus

log = logging.getLogger("gamblit_redeemer.accounts")


class ManagedAccount:
    def __init__(
        self,
        account_id: str,
        name: str,
        cookies: str,
        enabled: bool = True,
        config: Optional[Config] = None,
    ):
        self.id = account_id
        self.name = name
        self.raw_cookies = cookies
        self.enabled = enabled

        base_url = config.gamblit_base_url if config else "https://gamblit.co"
        ua = config.gamblit_user_agent if config else ""
        c_to = config.connect_timeout_sec if config else 3.0
        r_to = config.read_timeout_sec if config else 5.0
        retries = config.max_retries if config else 2

        self.config = Config(
            gamblit_base_url=base_url,
            raw_cookies=cookies,
            gamblit_user_agent=ua,
            connect_timeout_sec=c_to,
            read_timeout_sec=r_to,
            max_retries=retries,
        )
        self.client = GamblitClient(config=self.config)

    def to_dict(self) -> Dict[str, Any]:
        profile = self.client._profile
        is_auth = profile.is_authenticated if profile else False
        status_text = "Bağlı" if is_auth else ("Bağlantı Yok" if not self.client._connected else "Bağlanıyor...")
        
        # Format balance cleanly (e.g. 508.42 WL or DL)
        raw_bal = profile.balance_dl if profile and profile.balance_dl is not None else 0
        try:
            formatted_bal = round(float(raw_bal), 2)
        except Exception:
            formatted_bal = raw_bal

        # Dynamic name showing actual username once authenticated
        display_name = self.name
        if profile and is_auth and profile.username:
            if "efe2424" in display_name or "Ana Hesap" in display_name:
                display_name = f"Ana Hesap ({profile.username})"

        return {
            "id": self.id,
            "name": display_name,
            "raw_cookies": self.raw_cookies,
            "enabled": self.enabled,
            "username": profile.username if profile and is_auth else status_text,
            "is_authenticated": is_auth,
            "is_connected": self.client._connected,
            "balance_dl": formatted_bal,
            "level": self.level,
        }

    @property
    def level(self) -> int:
        if self.client and self.client._profile and self.client._profile.level is not None:
            try:
                return int(self.client._profile.level)
            except Exception:
                return 1
        return 1


class AccountManager:
    def __init__(self, config: Config, data_path: str = "data/accounts.json"):
        self.config = config
        self.data_path = Path(data_path)
        self.accounts: Dict[str, ManagedAccount] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if self.data_path.exists():
            try:
                with open(self.data_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        acc = ManagedAccount(
                            account_id=item.get("id", f"acc_{uuid.uuid4().hex[:6]}"),
                            name=item.get("name", "Hesap"),
                            cookies=item.get("raw_cookies", ""),
                            enabled=item.get("enabled", True),
                            config=self.config,
                        )
                        self.accounts[acc.id] = acc
            except Exception as e:
                log.error(f"Error loading accounts from {self.data_path}: {e}")

        # Also import accounts from GAMBLIT_ACCOUNTS env if provided
        if self.config.raw_accounts:
            try:
                env_accounts = json.loads(self.config.raw_accounts)
                if isinstance(env_accounts, list):
                    for item in env_accounts:
                        aid = item.get("id") or f"acc_{uuid.uuid4().hex[:6]}"
                        if aid not in self.accounts:
                            self.accounts[aid] = ManagedAccount(
                                account_id=aid,
                                name=item.get("name", "Hesap"),
                                cookies=item.get("raw_cookies", ""),
                                enabled=item.get("enabled", True),
                                config=self.config,
                            )
            except Exception as e:
                log.error(f"Error importing GAMBLIT_ACCOUNTS env: {e}")

        # Auto-import default account from GAMBLIT_COOKIES if list is still empty
        if not self.accounts and self.config.raw_cookies and self.config.raw_cookies != "{}":
            default_id = "acc_default"
            acc = ManagedAccount(
                account_id=default_id,
                name="Ana Hesap",
                cookies=self.config.raw_cookies,
                enabled=True,
                config=self.config,
            )
            self.accounts[default_id] = acc
            self._save()

    def _save(self):
        try:
            items = []
            for acc in self.accounts.values():
                items.append({
                    "id": acc.id,
                    "name": acc.name,
                    "raw_cookies": acc.raw_cookies,
                    "enabled": acc.enabled,
                })
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"Error saving accounts to {self.data_path}: {e}")

    async def start_all(self):
        """Connects WebSocket for all enabled accounts."""
        tasks = [acc.client.connect_ws() for acc in self.accounts.values() if acc.enabled]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close_all(self):
        """Closes connections for all accounts."""
        tasks = [acc.client.close() for acc in self.accounts.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def add_account(self, name: str, cookies: str) -> ManagedAccount:
        acc_id = f"acc_{uuid.uuid4().hex[:8]}"
        acc = ManagedAccount(
            account_id=acc_id,
            name=name.strip() or f"Hesap {len(self.accounts) + 1}",
            cookies=cookies.strip(),
            enabled=True,
            config=self.config,
        )
        self.accounts[acc.id] = acc
        self._save()
        asyncio.create_task(acc.client.connect_ws())
        log.info(f"Yeni hesap eklendi: '{acc.name}' (ID: {acc.id})")
        return acc

    async def remove_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            acc = self.accounts.pop(account_id)
            try:
                await acc.client.close()
            except Exception:
                pass
            self._save()
            log.info(f"Hesap silindi: '{acc.name}' (ID: {account_id})")
            return True
        return False

    async def toggle_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            acc = self.accounts[account_id]
            acc.enabled = not acc.enabled
            self._save()
            if acc.enabled:
                asyncio.create_task(acc.client.connect_ws())
            else:
                asyncio.create_task(acc.client.close())
            return True
        return False

    def get_max_level(self) -> int:
        """Returns the highest level among all enabled accounts."""
        active = [acc for acc in self.accounts.values() if acc.enabled]
        if not active:
            return 1
        return max((acc.level for acc in active), default=1)

    async def redeem_all(
        self,
        code: str,
        req_level: Optional[int] = None,
        captcha_token: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Redeems promo code across all eligible enabled accounts concurrently (in parallel).
        If req_level is specified, accounts with level < req_level are safely skipped without wasting requests.
        """
        active = [
            acc for acc in self.accounts.values()
            if acc.enabled and (req_level is None or req_level <= 0 or acc.level >= req_level)
        ]
        if not active:
            return []

        async def _redeem_one(acc: ManagedAccount) -> Dict[str, Any]:
            lat = RedeemLatency(t0_discord_received=time.time())
            res = await acc.client.redeem_code(code, latency=lat, captcha_token=captcha_token)
            return {
                "account_id": acc.id,
                "account_name": acc.name,
                "username": acc.client._profile.username if acc.client._profile else acc.name,
                "code": code,
                "req_level": req_level,
                "result": res,
            }

        results = await asyncio.gather(*[_redeem_one(acc) for acc in active], return_exceptions=True)
        out = []
        for r in results:
            if not isinstance(r, Exception):
                out.append(r)
        return out

    async def redeem_drop(
        self,
        level_codes: List[Tuple[int, str]],
        captcha_pool: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Redeems a multi-level drop across all active accounts concurrently.
        For each account, filters codes by (acc.level >= req_level) and executes redemption
        strictly in descending order (highest reward / highest required level first).
        Uses captcha tokens on-demand only when a challenge is received.
        """
        active = [acc for acc in self.accounts.values() if acc.enabled]
        if not active or not level_codes:
            return []

        async def _redeem_account(acc: ManagedAccount) -> List[Dict[str, Any]]:
            # 1. Filter codes this account is eligible for (acc.level >= req_lvl)
            # level_codes is already sorted descending by required level
            eligible = [(lvl, code) for lvl, code in level_codes if acc.level >= lvl]
            if not eligible:
                log.info(f"⏭️ [{acc.name}] (Level {acc.level}): Drop kodları seviyesinden yüksek, atlandı.")
                return []

            acc_results = []
            log.info(
                f"🚀 [{acc.name}] (Level {acc.level}): {len(eligible)} adet kod hakkı var! "
                f"En yüksek ödülden (Level {eligible[0][0]}+) başlayarak alınıyor..."
            )

            for req_lvl, code in eligible:
                log.info(f"⚡ [{acc.name}] -> Kod Gönderiliyor: '{code}' (Gereken Level: {req_lvl}+ | Hesap: {acc.level})")
                lat = RedeemLatency(t0_discord_received=time.time())

                # If token is pre-warmed in pool, take it instantly (0.1ms) for zero-latency redeem!
                token = ""
                if captcha_pool:
                    token = await captcha_pool.consume_token() or ""

                res = await acc.client.redeem_code(code, latency=lat, captcha_token=token)

                # If rejected by captcha and we hadn't sent a token, try fallback solve
                is_captcha_err = (
                    "CAPTCHA" in res.message.upper()
                    or (res.response_data and "CAPTCHA" in str(res.response_data).upper())
                )
                if is_captcha_err and captcha_pool and not token:
                    log.warning(f"🛡️ [{acc.name}] Captcha engeli ({res.message}). Yedek token çözülüyor...")
                    fresh_tok = await captcha_pool.consume_token()
                    if not fresh_tok:
                        fresh_tok = await captcha_pool.auto_solve_once()
                    if fresh_tok:
                        lat_retry = RedeemLatency(t0_discord_received=time.time())
                        res = await acc.client.redeem_code(code, latency=lat_retry, captcha_token=fresh_tok)

                acc_results.append({
                    "account_id": acc.id,
                    "account_name": acc.name,
                    "username": acc.client._profile.username if acc.client._profile else acc.name,
                    "code": code,
                    "req_level": req_lvl,
                    "result": res,
                })

                if res.status == RedeemStatus.SUCCESS:
                    log.info(f"🎉 [{acc.name}] BAŞARIYLA ALINDI! Kod: {code} (Level {req_lvl}+) | {res.message}")
                else:
                    log.info(f"📌 [{acc.name}] Kod: {code} -> {res.status.value} ({res.message})")

            return acc_results

        # Execute all accounts concurrently
        tasks = [_redeem_account(acc) for acc in active]
        nested_results = await asyncio.gather(*tasks, return_exceptions=True)

        flat_results = []
        for r in nested_results:
            if isinstance(r, list):
                flat_results.extend(r)
            elif isinstance(r, Exception):
                log.error(f"Error redeeming drop on account: {r}")

        return flat_results

    def get_summary(self) -> Dict[str, Any]:
        accs = [acc.to_dict() for acc in self.accounts.values()]
        connected_count = sum(1 for a in accs if a.get("is_authenticated") or a.get("is_connected"))
        total_dl = sum(a.get("balance_dl", 0) or 0 for a in accs)
        return {
            "total_accounts": len(accs),
            "connected_accounts": connected_count,
            "total_dl": total_dl,
            "accounts": accs,
        }
