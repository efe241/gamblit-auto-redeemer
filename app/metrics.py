"""
Latency and operational performance metrics tracker.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List
import time
from app.models import RedeemLatency, RedeemResult


class MetricsTracker:
    def __init__(self):
        self.start_time = time.time()
        self.total_received = 0
        self.total_parsed = 0
        self.total_success = 0
        self.total_failed = 0
        self.recent_latencies: List[float] = []
        self.last_result: Any = None

    def record_received(self):
        self.total_received += 1

    def record_parsed(self):
        self.total_parsed += 1

    def record_redeem(self, result: RedeemResult):
        self.last_result = result
        if result.success:
            self.total_success += 1
        else:
            self.total_failed += 1

        if result.latency.total_ms > 0:
            self.recent_latencies.append(result.latency.total_ms)
            if len(self.recent_latencies) > 100:
                self.recent_latencies.pop(0)

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def avg_latency_ms(self) -> float:
        if not self.recent_latencies:
            return 0.0
        return sum(self.recent_latencies) / len(self.recent_latencies)

    def format_latency_breakdown(self, latency: RedeemLatency) -> str:
        return (
            f"Discord -> Parser: {latency.parse_ms:.2f} ms | "
            f"Parser -> Request: {latency.queue_to_request_ms:.2f} ms | "
            f"HTTP: {latency.http_request_ms:.2f} ms | "
            f"Total: {latency.total_ms:.2f} ms"
        )

    def reset(self):
        self.total_received = 0
        self.total_parsed = 0
        self.total_success = 0
        self.total_failed = 0
        self.recent_latencies.clear()
        self.last_result = None

    def summary(self) -> Dict[str, Any]:
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "total_received": self.total_received,
            "total_parsed": self.total_parsed,
            "total_success": self.total_success,
            "total_failed": self.total_failed,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "last_code": self.last_result.code if self.last_result else None,
            "last_status": self.last_result.status.value if self.last_result else None,
        }

