"""Real price series for the backtest: fetch cached DefiLlama charts, bucket to the rule's
granularity, optionally denominate ETH-pegged assets vs ETH, and compute references.

All series are REAL DefiLlama data cached in data/raw/ (offline-safe). A leg with denom:'eth'
is divided by the ETH/USD series so an ETH-pegged asset's peg deviation is measured vs ETH
(not contaminated by ETH's own USD move)."""
from __future__ import annotations

import datetime as dt

from ..sources import defillama
from .library import denom_keys, load_rule

DAY = 86400
_SEC = {"1h": 3600, "4h": 4 * 3600, "1d": DAY}


def epoch(date_str: str) -> int:
    return int(dt.datetime.strptime(date_str, "%Y-%m-%d")
               .replace(tzinfo=dt.timezone.utc).timestamp())


def date_of(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


# DefiLlama's /chart caps a single request at ~500 points; fetch longer ranges in fixed
# deterministic chunks so offline replays hit the same cache keys.
_CHUNK = 450


def _raw_series(key: str, start: int, span: int, period: str) -> dict[int, float]:
    """{bucket_ts: price}, last sample per bucket. Auto-chunks spans over the API cap."""
    sec = _SEC[period]
    out: dict[int, float] = {}
    offset = 0
    while offset < span:
        this = min(_CHUNK, span - offset)
        raw = defillama.chart(key, start=start + offset * sec, span=this, period=period)
        pts = ((raw.get("coins") or {}).get(key) or {}).get("prices", [])
        for p in pts:
            out[round(p["timestamp"] / sec) * sec] = p["price"]
        offset += this
    return out


def _nearest(series: dict[int, float], ts: int, sec: int) -> float | None:
    for d in (0, sec, -sec, 2 * sec, -2 * sec):
        if ts + d in series:
            return series[ts + d]
    return None


def _denominate(series: dict[int, float], denom: str, start: int, span: int, period: str) -> dict[int, float]:
    if denom != "eth":
        return series
    eth = _raw_series(denom_keys()["eth"], start, span, period)
    sec = _SEC[period]
    out: dict[int, float] = {}
    for ts, px in series.items():
        e = _nearest(eth, ts, sec)
        if e:
            out[ts] = px / e
    return out


def load_leg(price_key: str, denom: str, start: int, span: int, period: str) -> dict[int, float]:
    """Return {bucket_ts: (denominated) price} for one leg over [start, start+span*sec]."""
    s = _raw_series(price_key, start, span, period)
    return _denominate(s, denom, start, span, period)


def forward_fill(series: dict[int, float], ts_list: list[int]) -> dict[int, float]:
    """Carry the last known price forward across the full timestamp grid."""
    out: dict[int, float] = {}
    last = None
    for ts in ts_list:
        if ts in series:
            last = series[ts]
        if last is not None:
            out[ts] = last
    return out


def median(vals: list[float]) -> float | None:
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def event_window(event: dict) -> dict:
    """Fetch + align both legs of an event; return grid, forward-filled prices, and references.

    Keys: period, sec, ts (sorted grid), up {ts:px}, dn {ts:px}, up_ref, dn_ref, event_ts."""
    rule = load_rule()
    period = rule["data"]["granularity"]
    sec = _SEC[period]
    pre, post = rule["data"]["window_pre_days"], rule["data"]["window_post_days"]
    ev = epoch(event["date"])
    start = ev - pre * DAY
    span = (pre + post) * (DAY // sec)

    up_raw = load_leg(event["upstream"]["price_key"], event["upstream"].get("denom", "usd"),
                      start, span, period)
    dn_raw = load_leg(event["downstream"]["price_key"], event["downstream"].get("denom", "usd"),
                      start, span, period)
    ts = sorted(set(up_raw) | set(dn_raw))
    up = forward_fill(up_raw, ts)
    dn = forward_fill(dn_raw, ts)

    ref_days = rule["reference"]["pre_event_median_days"]
    ref_lo = ev - ref_days * DAY
    up_ref = median([up[t] for t in ts if ref_lo <= t < ev and t in up])
    dn_ref = median([dn[t] for t in ts if ref_lo <= t < ev and t in dn])
    return {"period": period, "sec": sec, "ts": ts, "up": up, "dn": dn,
            "up_ref": up_ref, "dn_ref": dn_ref, "event_ts": ev}
