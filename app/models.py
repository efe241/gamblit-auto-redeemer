"""
Data models and Enums for Gamblit Promo Code Auto-Redeemer.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
import time


class RedeemStatus(str, Enum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    INVALID_CODE = "INVALID_CODE"
    EXPIRED = "EXPIRED"
    ALREADY_USED = "ALREADY_USED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        """Determines if the status is final and should not be retried."""
        return self in {
            RedeemStatus.SUCCESS,
            RedeemStatus.INVALID_CODE,
            RedeemStatus.EXPIRED,
            RedeemStatus.ALREADY_USED,
            RedeemStatus.NOT_ELIGIBLE,
        }

    @property
    def is_retryable(self) -> bool:
        """Determines if the request can safely be retried."""
        return self in {
            RedeemStatus.RATE_LIMITED,
            RedeemStatus.SERVER_ERROR,
            RedeemStatus.NETWORK_ERROR,
        }


@dataclass
class ParsedCode:
    code: str
    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    received_at: float = field(default_factory=time.time)
    parsed_at: float = field(default_factory=time.time)
    raw_content: str = ""
    required_level: Optional[int] = None
    level_codes: Optional[Any] = None  # List[Tuple[int, str]] if multi-level drop

    @property
    def parse_latency_ms(self) -> float:
        return max(0.0, (self.parsed_at - self.received_at) * 1000.0)


@dataclass
class RedeemLatency:
    t0_discord_received: float = 0.0
    t1_parsed: float = 0.0
    t2_request_started: float = 0.0
    t3_response_received: float = 0.0

    @property
    def parse_ms(self) -> float:
        if self.t1_parsed and self.t0_discord_received:
            return max(0.0, (self.t1_parsed - self.t0_discord_received) * 1000.0)
        return 0.0

    @property
    def queue_to_request_ms(self) -> float:
        if self.t2_request_started and self.t1_parsed:
            return max(0.0, (self.t2_request_started - self.t1_parsed) * 1000.0)
        return 0.0

    @property
    def http_request_ms(self) -> float:
        if self.t3_response_received and self.t2_request_started:
            return max(0.0, (self.t3_response_received - self.t2_request_started) * 1000.0)
        return 0.0

    @property
    def total_ms(self) -> float:
        if self.t3_response_received and self.t0_discord_received:
            return max(0.0, (self.t3_response_received - self.t0_discord_received) * 1000.0)
        return 0.0


@dataclass
class RedeemResult:
    code: str
    status: RedeemStatus
    message: str = ""
    status_code: Optional[int] = None
    response_data: Optional[Dict[str, Any]] = None
    latency: RedeemLatency = field(default_factory=RedeemLatency)
    attempts: int = 1
    retry_after: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.status == RedeemStatus.SUCCESS


@dataclass
class AccountProfile:
    username: str = ""
    user_id: Optional[str] = None
    level: Optional[int] = None
    balance_dl: Optional[float] = None
    balance_bgl: Optional[float] = None
    is_authenticated: bool = False
    last_checked_at: float = 0.0
