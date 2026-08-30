"""HubRoot LoRA metadata client.

InvokeAI stores no LoRA trigger words / descriptions on this box, but the model
hub (HubRoot v3, http://localhost:8000) does. Join by blake3 hash to recover a
LoRA's triggers/description/base so we can inject trigger words at generation
time and (later) search the library.
"""
import json
import time

import requests

BASE_URL = "http://localhost:8000"
_TTL = 300
_cache = {"index": None, "ts": 0.0}


def _norm_hash(h):
    return (h or "").split(":")[-1].strip().lower()


def _parse_triggers(val):
    if not val:
        return []
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        s = val.strip()
        try:
            j = json.loads(s)
            if isinstance(j, list):
                return [str(x).strip() for x in j if str(x).strip()]
        except (ValueError, TypeError):
            pass
        return [s] if s else []
    return []


def available():
    try:
        return requests.get(f"{BASE_URL}/api/models", params={"limit": 1}, timeout=4).ok
    except Exception:
        return False


def _fetch_all_loras():
    rows, offset = [], 0
    while offset <= 10000:
        r = requests.get(
            f"{BASE_URL}/api/models",
            params={"model_type": "lora", "limit": 1000, "offset": offset, "deleted": 0},
            timeout=12,
        )
        r.raise_for_status()
        d = r.json()
        items = d.get("items", d.get("models", []))
        if not items:
            break
        rows.extend(items)
        if len(items) < 1000:
            break
        offset += 1000
    return rows


def _index():
    now = time.time()
    if _cache["index"] is not None and now - _cache["ts"] < _TTL:
        return _cache["index"]
    idx = {}
    try:
        for m in _fetch_all_loras():
            hb = _norm_hash(m.get("hash_blake3"))
            if hb:
                idx[hb] = m
    except Exception:
        idx = _cache["index"] or {}
    _cache["index"] = idx
    _cache["ts"] = now
    return idx


def meta_for(blake3_hash):
    """Return {name, triggers, description, base} for a LoRA by blake3, or None."""
    row = _index().get(_norm_hash(blake3_hash))
    if not row:
        return None
    return {
        "name": row.get("name"),
        "triggers": _parse_triggers(row.get("triggers")),
        "description": row.get("description"),
        "base": row.get("base_model"),
    }


def triggers_for(blake3_hash):
    m = meta_for(blake3_hash)
    return m["triggers"] if m else []


def search(query, base=None, limit=25):
    """Search the LoRA library (for the add/remove picker). Returns raw rows."""
    params = {"model_type": "lora", "limit": limit, "search": query or "", "deleted": 0}
    if base:
        params["base_model"] = base
    try:
        r = requests.get(f"{BASE_URL}/api/models", params=params, timeout=8)
        r.raise_for_status()
        d = r.json()
        return d.get("items", d.get("models", []))
    except Exception:
        return []
