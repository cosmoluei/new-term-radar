"""Is this term the name of a new thing, or a common word?

The signals surface whatever is new in the text they read: "Opus 5.5" and "HyperFrames",
but also "Lots", "Trained" and "voice notes". A model (optional) reads each term with a
few places it appeared and scores it from 0 to 1; without a key a local heuristic does
the same. The report leads with the names.

Chat goes through ``radar.llm`` (OpenAI-compatible, DeepSeek, or AIsa). The model is
set in config.json (judge.model). Set it to "heuristic" to force the local scorer.
The judge sorts the report; it never blocks it.
"""
from __future__ import annotations

import json
import re

from . import llm

CHUNK = 25
SYSTEM = (
    "You sort terms for a radar that looks for new product names. For each term, score from 0.0 to 1.0 how likely "
    "it is the NAME of one specific product, model, tool, library, company or technique, as opposed to a common "
    "word, a generic category, a feature description or a fragment of a sentence. `examples` are places where the "
    "term appeared (posts, repository descriptions, model ids, URL paths); use them.\n"
    "Names: 'opus 5.5', 'hyperframes', 'seedance', 'qwen image 2.1', 'strata' (when the examples show a project "
    "called Strata).\n"
    "Not names: 'dashboard', 'voice notes', 'pdf', 'lots', 'trained', 'video generator', 'new release', 'today'.\n"
    "A known company or product family alone ('google', 'claude') is a name, but an old one: score it 0.5.\n"
    "Answer with JSON only, one object per term, in the same order: [{\"i\": 0, \"score\": 0.9}, ...]"
)

_DIGIT = re.compile(r"\d")
_INNER_CAP = re.compile(r"[a-z][A-Z]")  # unused on lowercased terms; use digit / length instead
_GENERIC = {
    "dashboard", "voice notes", "pdf", "lots", "trained", "video generator", "new release", "today",
    "math", "anatomy", "support", "update", "release", "announcement", "thread", "paper", "report",
}


def parse(answer: str, n: int) -> dict[int, float]:
    """{index: score} from the model's answer; indexes outside 0..n-1 and bad scores are dropped."""
    m = re.search(r"\[.*\]", answer, re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        return {}
    out = {}
    for it in items if isinstance(items, list) else []:
        try:
            i, score = int(it["i"]), float(it["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= i < n and 0.0 <= score <= 1.0:
            out[i] = score
    return out


def heuristic_score(term: str, examples: list[str]) -> float:
    """Cheap local stand-in for the chat judge: prefer versioned / product-like names."""
    t = (term or "").strip().lower()
    if not t or t in _GENERIC:
        return 0.15
    score = 0.35
    if _DIGIT.search(t):
        score += 0.4
    parts = t.split()
    if len(parts) >= 2:
        score += 0.15
    if len(parts) >= 3:
        score += 0.1
    # Repo-style examples (owner/name) strongly suggest a product.
    blob = " ".join(examples[:3]).lower()
    if "/" in blob and any(p in blob for p in parts if len(p) >= 3):
        score += 0.2
    if t in blob.replace("-", " ").replace("_", " "):
        score += 0.05
    # Very short single tokens without digits are usually ordinary words.
    if len(parts) == 1 and len(t) <= 5 and not _DIGIT.search(t):
        score -= 0.15
    return max(0.0, min(1.0, round(score, 2)))


def heuristic(rows: list[dict]) -> dict:
    for r in rows:
        r["named"] = heuristic_score(r["term"], r.get("examples") or [])
    return {"judged": len(rows), "backend": "heuristic"}


def score(rows: list[dict], model: str) -> dict:
    """Sets r["named"] on each row the model scored. Returns {"judged": n} or {"error": ...}."""
    if not rows:
        return {"judged": 0}
    if not model or model == "heuristic" or not llm.available():
        return heuristic(rows)
    judged = 0
    for start in range(0, len(rows), CHUNK):
        chunk = rows[start:start + CHUNK]
        user = json.dumps([{"i": i, "term": r["term"], "examples": [e[:160] for e in r.get("examples", [])[:3]]}
                           for i, r in enumerate(chunk)], ensure_ascii=False)
        try:
            scores = parse(llm.chat(model, SYSTEM, user), len(chunk))
        except llm.LLMError as exc:
            # Prefer a sorted report over an empty one.
            h = heuristic(rows)
            h["error"] = str(exc)[:160]
            h["backend"] = "heuristic"
            return h
        for i, s in scores.items():
            chunk[i]["named"] = s
        judged += len(scores)
    return {"judged": judged, "backend": "llm"}
