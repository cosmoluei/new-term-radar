"""Fetch recent posts for the X accounts without AIsa.

Backends, tried in order:

1. ``X_POSTS_FILE`` (path) or ``state/x_posts.json`` if present and fresh enough —
   a pre-fetched dump. Grok Bot (or any script) can write this via the X MCP /
   API and the radar never needs a paid X proxy.
2. ``X_BEARER_TOKEN`` — official X API v2 (user lookup + user timeline).
3. ``AISA_API_KEY`` — legacy ``get_twitter_user_last_tweets`` (optional).

A missing backend raises ``XUnavailable`` so the signal can skip cleanly.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import UA, aisa

# A dump older than this is ignored so a stale file cannot hide a missing key.
DUMP_MAX_AGE_HOURS = 36
X_API = "https://api.x.com/2"
PER_USER = 20          # last N posts per account (AIsa used ~20)
TIMEOUT = 40


class XUnavailable(RuntimeError):
    pass


def _iso(dt: datetime | None) -> datetime | None:
    return dt


def parse_created(value) -> datetime | None:
    """Accept AIsa's Twitter date, X API ISO-8601, or a datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except ValueError:
        pass
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def normalize_post(account: str, raw: dict) -> dict:
    """One post in the shape ``sources.novel_names`` expects."""
    text = raw.get("text") or ""
    likes = raw.get("likes")
    if likes is None:
        metrics = raw.get("public_metrics") or {}
        likes = metrics.get("like_count") or raw.get("likeCount") or 0
    url = raw.get("url") or ""
    if not url and raw.get("id"):
        url = f"https://x.com/{account}/status/{raw['id']}"
    created = parse_created(raw.get("created") or raw.get("created_at") or raw.get("createdAt"))
    return {"account": account, "text": text, "likes": int(likes or 0), "url": url, "created": created}


def load_dump(path: Path) -> list[dict] | None:
    """Posts from a JSON dump, or None if missing / too old / unreadable."""
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    fetched = parse_created(body.get("fetched_at"))
    if fetched and datetime.now(timezone.utc) - fetched > timedelta(hours=DUMP_MAX_AGE_HOURS):
        return None
    posts = []
    for raw in body.get("posts") or []:
        account = (raw.get("account") or raw.get("username") or "").lstrip("@")
        if not account:
            continue
        posts.append(normalize_post(account, raw))
    return posts


def _http_json(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers={**headers, "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
            return json.load(res)
    except urllib.error.HTTPError as exc:
        raise XUnavailable(f"X API HTTP {exc.code}: {' '.join(exc.read().decode('utf-8', 'replace').split())[:160]}") from exc
    except (OSError, ValueError) as exc:
        raise XUnavailable(f"{type(exc).__name__}: {exc}") from exc


def fetch_via_bearer(handles: list[str], token: str) -> list[dict]:
    """X API v2: resolve usernames, then each user's recent posts."""
    headers = {"Authorization": f"Bearer {token}"}
    # Lookup in chunks of 100 (API limit).
    id_of: dict[str, str] = {}
    for i in range(0, len(handles), 100):
        chunk = handles[i:i + 100]
        q = urllib.parse.urlencode({"usernames": ",".join(chunk), "user.fields": "id,username"})
        data = _http_json(f"{X_API}/users/by?{q}", headers)
        for u in data.get("data") or []:
            id_of[u["username"].lower()] = u["id"]
    posts = []
    fields = "id,text,created_at,public_metrics"
    for h in handles:
        uid = id_of.get(h.lower())
        if not uid:
            continue
        q = urllib.parse.urlencode({"max_results": PER_USER, "tweet.fields": fields,
                                    "exclude": "retweets,replies"})
        try:
            data = _http_json(f"{X_API}/users/{uid}/tweets?{q}", headers)
        except XUnavailable:
            continue
        for tw in data.get("data") or []:
            posts.append(normalize_post(h, tw))
    return posts


def fetch_via_aisa(handles: list[str]) -> tuple[list[dict], int]:
    data, cost = aisa.call_all([{"call_id": h, "tool": "get_twitter_user_last_tweets",
                                 "arguments": {"userName": h}} for h in handles])
    posts = []
    for h in handles:
        for tw in ((data.get(h) or {}).get("data") or {}).get("tweets") or []:
            posts.append(normalize_post(h, tw))
    return posts, cost


def fetch_posts(handles: list[str], state: Path) -> tuple[list[dict], dict]:
    """Returns (posts, meta). meta has backend, cost_micros, answered."""
    env_path = os.environ.get("X_POSTS_FILE", "").strip()
    for path in ([Path(env_path)] if env_path else []) + [state / "x_posts.json"]:
        dumped = load_dump(path)
        if dumped is not None:
            accounts = {p["account"] for p in dumped}
            return dumped, {"backend": "dump", "path": str(path), "answered": len(accounts), "cost_micros": 0}

    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if token:
        posts = fetch_via_bearer(handles, token)
        answered = len({p["account"] for p in posts})
        return posts, {"backend": "x_api", "answered": answered, "cost_micros": 0}

    if aisa.available():
        posts, cost = fetch_via_aisa(handles)
        return posts, {"backend": "aisa", "answered": len({p["account"] for p in posts}), "cost_micros": cost}

    raise XUnavailable(
        "no X backend: write state/x_posts.json (see scripts/fetch_x_posts.py), "
        "or set X_BEARER_TOKEN, or set AISA_API_KEY"
    )
