"""Disk cache for API responses.

Every outbound HTTP call is written through to ``data/raw/`` so the whole demo
runs offline and is byte-for-byte reproducible. Set ``BLAST_RADIUS_OFFLINE=1`` to
forbid network access entirely (used to prove the cached demo works unplugged).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import requests

# blast_radius/sources/cache.py -> parents[2] == repo root
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TIMEOUT = 40


def _pace() -> None:
    """Optional polite delay on live misses only (zero cost on cache hits)."""
    delay = float(os.environ.get("BLAST_RADIUS_HTTP_DELAY", "0"))
    if delay > 0:
        time.sleep(delay)


def _offline() -> bool:
    return os.environ.get("BLAST_RADIUS_OFFLINE", "0") == "1"


def _key(method: str, url: str, params: Any = None, body: Any = None) -> str:
    blob = json.dumps(
        {"m": method, "u": url, "p": params, "b": body}, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


def _path(key: str) -> Path:
    return RAW_DIR / f"{key}.json"


def _read(key: str) -> Optional[Any]:
    p = _path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))["data"]
    except Exception:
        return None


def _write(key: str, meta: dict, data: Any) -> None:
    payload = {"meta": meta, "data": data, "cached_at": time.time()}
    _path(key).write_text(json.dumps(payload), encoding="utf-8")


def cached_get(
    url: str,
    params: Any = None,
    headers: Any = None,
    label: str = "",
    force: bool = False,
) -> Any:
    key = _key("GET", url, params=params)
    if not force:
        hit = _read(key)
        if hit is not None:
            return hit
    if _offline():
        raise RuntimeError(f"OFFLINE: no cache for GET {url} params={params} (key={key})")
    _pace()
    r = requests.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    _write(key, {"method": "GET", "url": url, "params": params, "label": label}, data)
    return data


def cached_post(
    url: str,
    json_body: Any,
    headers: Any = None,
    label: str = "",
    force: bool = False,
) -> Any:
    key = _key("POST", url, body=json_body)
    if not force:
        hit = _read(key)
        if hit is not None:
            return hit
    if _offline():
        raise RuntimeError(f"OFFLINE: no cache for POST {url} (key={key})")
    _pace()
    r = requests.post(url, json=json_body, headers=headers, timeout=DEFAULT_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    _write(key, {"method": "POST", "url": url, "label": label}, data)
    return data


def cache_stats() -> dict:
    files = list(RAW_DIR.glob("*.json"))
    return {"dir": str(RAW_DIR), "files": len(files),
            "bytes": sum(f.stat().st_size for f in files)}


def cached_text(url: str) -> str:
    """Cache primary-source documentation alongside JSON API evidence."""
    key = _key("GET_TEXT", url)
    hit = _read(key)
    if hit is not None:
        return hit
    if _offline():
        raise RuntimeError(f"OFFLINE: no cached text for {url}")
    _pace()
    response = requests.get(url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    _write(key, {"method": "GET_TEXT", "url": url, "label": "manual_map_evidence"}, response.text)
    return response.text
