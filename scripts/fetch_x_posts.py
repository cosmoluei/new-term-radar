#!/usr/bin/env python3
"""Write state/x_posts.json for the radar's free X backend.

Two ways to fill the dump (no AIsa):

1. Official X API — set X_BEARER_TOKEN and run:
     python scripts/fetch_x_posts.py --config config.json --state state

2. Hand the radar posts you already have (e.g. Grok Bot's X MCP). Pipe JSON:
     echo '{"posts":[{"account":"OpenAI","text":"...","likes":10,
            "created":"2026-10-13T01:00:00+00:00","url":"https://x.com/..."}]}' \\
       | python scripts/fetch_x_posts.py --state state --stdin

The dump is ignored when older than 36 hours so a stale file cannot hide a
missing token. Refresh it before each `sources` run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from radar import config, sources, xclient  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.json")
    p.add_argument("--state", default="state")
    p.add_argument("--stdin", action="store_true", help="read a dump (or {posts:[...]}) from stdin")
    p.add_argument("--out", help="write here instead of STATE/x_posts.json")
    args = p.parse_args()
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else state / "x_posts.json"

    if args.stdin:
        body = json.load(sys.stdin)
        posts = body.get("posts", body if isinstance(body, list) else [])
        dump = {"fetched_at": body.get("fetched_at") or datetime.now(timezone.utc).isoformat(),
                "posts": posts, "source": body.get("source", "stdin")}
    else:
        cfg = config.load(Path(args.config))
        handles = sources.accounts(cfg)
        if not handles:
            print("no x_accounts in config", file=sys.stderr)
            return 1
        import os
        token = os.environ.get("X_BEARER_TOKEN", "").strip()
        if not token:
            print("set X_BEARER_TOKEN, or pass --stdin with a posts dump", file=sys.stderr)
            return 1
        posts = xclient.fetch_via_bearer(handles, token)
        dump = {"fetched_at": datetime.now(timezone.utc).isoformat(),
                "posts": [{"account": p["account"], "text": p["text"], "likes": p["likes"],
                           "url": p["url"], "created": p["created"].isoformat() if p["created"] else None}
                          for p in posts],
                "source": "x_api"}

    out.write_text(json.dumps(dump, ensure_ascii=False, indent=1))
    print(f"wrote {out} ({len(dump['posts'])} posts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
