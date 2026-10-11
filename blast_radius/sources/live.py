"""Run-local HTTP observations. Never read or write the historical disk cache."""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import time

import requests


class LiveInputError(ValueError):
    pass


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def timestamp(value) -> float:
    try:
        if isinstance(value, bool):
            raise ValueError()
        if isinstance(value, (int, float)):
            result = float(value)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError()
            result = dt.timestamp()
        if not math.isfinite(result):
            raise ValueError()
        return result
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise LiveInputError(f"Missing or invalid provider timestamp: {value!r}") from exc


def utc(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def number(value, label: str, *, positive=False, signed=False) -> float:
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError()
        n = float(value)
        if not math.isfinite(n) or (not signed and n < 0) or (positive and n <= 0):
            raise ValueError()
        return n
    except (ValueError, TypeError, OverflowError) as exc:
        raise LiveInputError(f"Incomplete or invalid {label}") from exc


@dataclass(frozen=True)
class FreshnessPolicy:
    risk_seconds: int = 900
    mark_seconds: int = 120
    quote_seconds: int = 120
    rpc_seconds: int = 120
    max_skew_seconds: int = 900
    future_tolerance_seconds: int = 15
    capture_budget_seconds: int = 180

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in asdict(self).values()):
            raise LiveInputError("Freshness policy limits must be positive integer seconds")

    def to_dict(self):
        return asdict(self)


class ObservationClient:
    def __init__(self, *, session=None, clock=time.time, policy=None, replay=None):
        self.session = session or requests.Session()
        self.clock = clock
        self.policy = policy or FreshnessPolicy()
        self.started_at = clock()
        self.observations = []
        self._memo = {}
        self._replay = {r["key"]: r for r in replay} if replay is not None else None
        if replay is not None:
            self._replay_time = self.started_at
            self.clock = lambda: self._replay_time
        self.rate_limited = False

    def request(self, method, url, *, params=None, body=None):
        request = {"method": method, "url": url, "params": params, "body": body}
        key = digest(request)
        if key in self._memo:
            record = self._memo[key]
        else:
            if self._replay is not None:
                if key not in self._replay:
                    raise LiveInputError(f"Receipt is missing observation for {url}")
                record = copy.deepcopy(self._replay[key])
                if record["request"] != request or record["key"] != digest(record["request"]):
                    raise LiveInputError("Observation request identity mismatch")
                self._replay_time = max(self._replay_time, record["received_at"])
            else:
                record = {"key": key, "request": request, "requested_at": self.clock()}
                try:
                    if self.rate_limited:
                        raise LiveInputError("Rate limited; refresh later (no retries or historical substitution)")
                    if self.clock() - self.started_at > self.policy.capture_budget_seconds:
                        raise LiveInputError("Live capture deadline exceeded")
                    response = self.session.request(method, url, params=params, json=body,
                                                    timeout=(3.05, 12))
                    record["http_status"] = response.status_code
                    record["headers"] = {k: v for k, v in response.headers.items()
                                         if k.lower() in ("date", "age", "retry-after", "x-computing-unit")
                                         or k.lower().startswith("x-ratelimit")}
                    if response.status_code == 429:
                        self.rate_limited = True
                    response.raise_for_status()
                    data = response.json()
                    # Reject NaN/Infinity JSON, even if a lenient HTTP parser accepts it.
                    digest(data)
                    record["response"] = data
                    if isinstance(data, dict) and (data.get("errors") or data.get("error")):
                        raise LiveInputError("API reported errors: " + str(data.get("errors") or data["error"])[:400])
                except (requests.RequestException, ValueError, TypeError) as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"[:600]
                record["received_at"] = self.clock()
            self._memo[key] = record
            self.observations.append(record)
        if record.get("error"):
            raise LiveInputError(record["error"])
        return copy.deepcopy(record["response"]), key

    def get(self, url, params=None):
        return self.request("GET", url, params=params)

    def post(self, url, body):
        return self.request("POST", url, body=body)


def check_time(value, now, max_age, policy, label):
    observed = timestamp(value)
    age = now - observed
    if age < -policy.future_tolerance_seconds or age > max_age:
        raise LiveInputError(f"Stale or future {label}: age {age:.1f}s; maximum {max_age}s")
    return observed
