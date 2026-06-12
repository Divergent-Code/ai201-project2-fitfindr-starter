"""
agent.py

The FitFindr planning loop. Orchestrates the tools in response to a natural
language user query, passing state between them via a single `session` dict.

The loop is sequential with conditional branches:
  - empty search results trigger a deterministic retry/fallback,
  - a still-empty search short-circuits to an error and returns early,
  - the two stretch tools (compare_price, check_trends) are non-fatal:
    a failure degrades to None/empty and never aborts the happy path.

Stretch features wired here: deterministic retry-with-fallback, the two
non-fatal stretch tools, and cross-session Style Profile Memory persisted to
data/style_profile.json.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent("vintage graphic tee under $30, size M",
                       get_example_wardrobe())
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
    check_trends,
)

# data/style_profile.json — user-generated state, git-ignored.
_PROFILE_PATH = os.path.join(os.path.dirname(__file__), "data", "style_profile.json")


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize a fresh session dict (the single source of truth for one run)."""
    return {
        "query": query,
        "parsed": {},                # {description, size, max_price}
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "style_profile": None,       # stretch: loaded preference text
        "fallback_used": False,      # stretch: True if constraints relaxed
        "warning": None,             # stretch: human-readable note on relaxation
        "price_assessment": None,    # stretch: from compare_price
        "trends": None,              # stretch: from check_trends
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,               # None on success; set => early return
    }


# ── query parsing ─────────────────────────────────────────────────────────────

# Triggers that introduce a user's standing style preference (for Style Memory).
_PREF_TRIGGER = re.compile(
    r"\bi (?:mostly|usually|normally|typically|often|always|generally|like to|love to)?\s*"
    r"(?:wear|rock|live in|style|gravitate toward)\b([^.!?]*)",
    re.IGNORECASE,
)


def _parse_query(query: str) -> tuple[dict, list[str]]:
    """
    Parse natural language into search parameters and standing preferences.

    Deterministic regex parsing (no LLM) — robust, offline, and easy to test.

    Returns:
        (parsed, preferences) where parsed = {description, size, max_price}
        and preferences is a list of style-preference phrases to merge into the
        Style Profile Memory.
    """
    lower = query.lower()
    spans: list[tuple[int, int]] = []  # spans to strip out of the description

    # --- max_price ---
    max_price = None
    m = re.search(
        r"(?:under|below|less than|max(?:imum)?|up to|<)\s*\$?\s*(\d+(?:\.\d+)?)",
        lower,
    )
    if not m:
        m = re.search(r"\$\s*(\d+(?:\.\d+)?)", lower)
    if m:
        max_price = float(m.group(1))
        spans.append(m.span())

    # --- size ---
    size = None
    sm = re.search(r"\bsize\s+([a-z0-9./]+)", lower)
    if not sm:
        sm = re.search(r"\bin\s+(?:a\s+)?(xxs|xs|s|m|l|xl|xxl)\b", lower)
    if sm:
        size = sm.group(1).upper()
        spans.append(sm.span())

    # --- standing style preferences (for Style Memory) ---
    preferences: list[str] = []
    for pm in _PREF_TRIGGER.finditer(query):
        phrase = pm.group(1).strip(" ,.")
        if phrase:
            preferences.append(phrase)
        spans.append(pm.span())

    # --- description = query with the matched spans removed ---
    chars = list(query)
    for start, end in spans:
        for i in range(start, min(end, len(chars))):
            chars[i] = " "
    description = re.sub(r"\s+", " ", "".join(chars)).strip()

    parsed = {"description": description, "size": size, "max_price": max_price}
    return parsed, preferences


# ── Style Profile Memory (stretch) ─────────────────────────────────────────────

def _load_style_profile() -> str | None:
    """Read data/style_profile.json; return its `preferences` text or None."""
    if not os.path.exists(_PROFILE_PATH):
        return None
    try:
        with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        prefs = (data or {}).get("preferences")
        return prefs or None
    except (json.JSONDecodeError, OSError):
        return None


def _save_style_profile(new_phrases: list[str]) -> None:
    """
    Merge newly detected preference phrases into data/style_profile.json
    (append-if-new, case-insensitive dedup) so prior sessions are preserved.
    """
    if not new_phrases:
        return
    existing = _load_style_profile() or ""
    existing_lower = existing.lower()

    additions = [
        p for p in new_phrases
        if p and p.lower() not in existing_lower
    ]
    if not additions:
        return

    merged = "; ".join(filter(None, [existing.strip("; ").strip(), *additions]))
    os.makedirs(os.path.dirname(_PROFILE_PATH), exist_ok=True)
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"preferences": merged}, f, indent=2)


# ── retry / fallback (stretch) ──────────────────────────────────────────────

def _search_with_fallback(session: dict) -> None:
    """
    Run search_listings, and on an empty result retry in the deterministic
    order: (a) drop max_price -> (b) drop size -> (c) drop both. Stop at the
    first non-empty result and record fallback_used + a human-readable warning.
    Writes session["search_results"], ["fallback_used"], ["warning"].
    """
    p = session["parsed"]
    desc, size, max_price = p["description"], p["size"], p["max_price"]

    results = search_listings(desc, size, max_price)
    if results:
        session["search_results"] = results
        return

    # (try_size, try_price, relaxed-description)
    attempts = [
        (size, None, f"the ${max_price:.0f} price limit" if max_price else None),
        (None, max_price, f"the size {size} filter" if size else None),
        (None, None, "both the size and price filters"),
    ]
    for try_size, try_price, relaxed in attempts:
        # Skip no-op attempts whose constraints equal the original search.
        if try_size == size and try_price == max_price:
            continue
        results = search_listings(desc, try_size, try_price)
        if results:
            session["search_results"] = results
            session["fallback_used"] = True
            session["warning"] = (
                f"No exact matches — relaxed {relaxed} to find these."
            )
            return

    # All retries exhausted: leave search_results empty (caller sets error).
    session["search_results"] = []


# ── non-fatal stretch-tool wrapper ──────────────────────────────────────────

def _safe(fn, *args, default=None):
    """Run a non-fatal stretch tool; degrade to `default` on any exception."""
    try:
        return fn(*args)
    except Exception:
        return default


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for one interaction
    and returns the completed session dict. Check session["error"] first — if
    not None, the run ended early and outfit_suggestion/fit_card are None.
    """
    session = _new_session(query, wardrobe)

    # [1] Load style profile (stretch).
    session["style_profile"] = _load_style_profile()

    # [2] Parse the query into search params + standing preferences.
    parsed, preferences = _parse_query(query)
    session["parsed"] = parsed

    # [3]/[4] Search, with deterministic retry/fallback on empty results.
    _search_with_fallback(session)

    if not session["search_results"]:
        size, max_price = parsed["size"], parsed["max_price"]
        loosen = []
        if max_price is not None:
            loosen.append("raising the price limit")
        if size is not None:
            loosen.append("removing the size")
        hint = (
            f" Try {', or '.join(loosen)}, or different keywords."
            if loosen
            else " Try different keywords."
        )
        session["error"] = (
            f'No listings matched "{parsed["description"] or query}".{hint}'
        )
        return session  # early return — skip all downstream tools

    # [5] Select the top match.
    item = session["search_results"][0]
    session["selected_item"] = item

    # [6] Price comparison (stretch, non-fatal).
    session["price_assessment"] = _safe(compare_price, item)

    # [7] Trends (stretch, non-fatal). Empty string is treated as None.
    trends = _safe(check_trends, item["category"], item.get("style_tags"))
    session["trends"] = trends or None

    # [8] Outfit suggestion (uses trends + style profile when present).
    session["outfit_suggestion"] = suggest_outfit(
        item, wardrobe, session["trends"], session["style_profile"]
    )

    # [9] Fit card (weaves in the price note when present).
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], item, session["price_assessment"]
    )

    # [10] Persist newly detected preferences for future sessions (stretch).
    _save_style_profile(preferences)

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        if session["warning"]:
            print(f"Warning: {session['warning']}")
        print(f"\nPrice check: {session['price_assessment']}")
        print(f"\nTrends: {session['trends']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== Retry/fallback path: under $10 (cheapest is $12) ===\n")
    session_r = run_agent(
        query="vintage graphic tee under $10",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Warning: {session_r['warning']}")
    print(f"Selected: {session_r['selected_item']['title'] if session_r['selected_item'] else None}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")

    # ── Style Profile Memory: two interactions, no re-entry (stretch) ──────────
    # Session A states a standing preference; session B never restates it, yet
    # the agent reuses it from data/style_profile.json. The proof (the loaded
    # profile) is set at step 1, before any LLM call, so this demo is meaningful
    # even without a Groq key.
    print("\n\n=== Style Profile Memory: session A saves, session B reuses ===\n")

    # Start from a clean slate so the demo is reproducible (file is git-ignored).
    if os.path.exists(_PROFILE_PATH):
        os.remove(_PROFILE_PATH)
    print(f"Profile before session A: {_load_style_profile()!r}")

    print("\n--- Session A (states a preference) ---")
    query_a = (
        "I'm looking for a vintage graphic tee under $30. "
        "I mostly wear baggy jeans and chunky sneakers."
    )
    session_a = run_agent(query_a, get_example_wardrobe())
    print(f"Query A: {query_a}")
    print(f"Found: {session_a['selected_item']['title'] if session_a['selected_item'] else None}")
    print(f"Profile saved to disk after session A: {_load_style_profile()!r}")

    print("\n--- Session B (NEW query, never restates the preference) ---")
    query_b = "show me a 90s denim jacket"
    parsed_b, prefs_b = _parse_query(query_b)
    session_b = run_agent(query_b, get_example_wardrobe())
    print(f"Query B: {query_b}")
    print(f"New preferences parsed from query B: {prefs_b}  (none — not restated)")
    print(f"Style profile the agent loaded & used in session B: {session_b['style_profile']!r}")
    print(
        "\n=> Session B reused 'baggy jeans and chunky sneakers' from session A "
        "without the user re-entering it."
    )
