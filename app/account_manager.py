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
from typing import Dict, List, Optional, Any
from app.config import Config
from app.gamblit_client import GamblitClient
from app.models import AccountProfile, RedeemResult, RedeemLatency

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
        return {
            "id": self.id,
            "name": self.name,
            "raw_cookies": self.raw_cookies,
            "enabled": self.enabled,
            "username": profile.username if profile and is_auth else status_text,
            "is_authenticated": is_auth,
            "is_connected": self.client._connected,
            "balance_dl": profile.balance_dl if profile else 0,
            "level": profile.level if profile else 1,
        }


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

        # Auto-import default account from .env if list is empty
        if not self.accounts and self.config.raw_cookies and self.config.raw_cookies != "{}":
            default_id = "acc_default"
            acc = ManagedAccount(
                account_id=default_id,
                name="Ana Hesap (efe2424)",
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

    async def redeem_all(self, code: str, captcha_token: str = "") -> List[Dict[str, Any]]:
        """
        Redeems promo code across all enabled accounts concurrently (in parallel).
        """
        active = [acc for acc in self.accounts.values() if acc.enabled]
        if not active:
            return []

        async def _redeem_one(acc: ManagedAccount) -> Dict[str, Any]:
            lat = RedeemLatency(t0_discord_received=time.time())
            res = await acc.client.redeem_code(code, latency=lat, captcha_token=captcha_token)
            return {
                "account_id": acc.id,
                "account_name": acc.name,
                "username": acc.client._profile.username if acc.client._profile else acc.name,
                "result": res,
            }

        results = await asyncio.gather(*[_redeem_one(acc) for acc in active], return_exceptions=True)
        out = []
        for r in results:
            if not isinstance(r, Exception):
                out.append(r)
        return out

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
