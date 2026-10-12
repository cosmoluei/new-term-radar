# Running without AIsa

Cosmo's fork prefers a **zero-AIsa** path. Paid DataForSEO / Trends / whois /
usecase evidence still need `AISA_API_KEY` if you want them; everything else runs free.

## What works with no paid keys

| Signal | Backend |
|---|---|
| ① X | `state/x_posts.json` dump, or `X_BEARER_TOKEN` (X API v2) |
| ① Hugging Face | public API |
| ② GitHub breakout | public API (`GITHUB_TOKEN` optional for higher rate limits) |
| ③ sitemaps | public HTTP |
| name judge | local `heuristic` (default), or `LLM_API_KEY` / OpenAI / DeepSeek |

## What still needs AIsa

- ③ new sites (whois overview)
- ⑤ review (Google Trends via DataForSEO)
- usecases / keyword table (X advanced search + Ads volume + Trends + chat)

Without `AISA_API_KEY` the CLI auto-skips those three.

## Free X reads

GitHub Actions cannot call Grok Bot's X MCP. Pick one:

1. **Dump (recommended for Cosmo)** — Grok Bot refreshes `state/x_posts.json` via the X MCP (`get_users_by_usernames` + `get_users_posts`), then runs `python -m radar sources` on the box, or restores the dump into the Actions `state` cache before a run. See `scripts/fetch_x_posts.py`. Dumps older than 36 hours are ignored.

2. **Official X API** — set repository secret `X_BEARER_TOKEN`. Free/basic tiers are rate-limited; ~35 accounts × 3/day may exceed free quotas.

3. **Legacy AIsa** — still supported if `AISA_API_KEY` is set and no dump/bearer is present.

## Optional cheap chat judge

Set `judge.model` to a chat model id and one of `LLM_API_KEY`, `OPENAI_API_KEY`, or `DEEPSEEK_API_KEY`. Otherwise keep `"judge": {"model": "heuristic"}`.
