"""
tools.py

The FitFindr tools. Each tool is a standalone function that can be called and
tested independently before being wired into the agent loop (see agent.py).

Required tools keep their locked two-argument interfaces; every stretch
parameter is appended after the required positional params and defaults to
None, so the required calls (and the Milestone 5 CLI commands) work unchanged.

Tools:
    search_listings(description, size, max_price)                    -> list[dict]
    suggest_outfit(new_item, wardrobe, trends, style_profile)        -> str
    create_fit_card(outfit, new_item, price_assessment)             -> str
    compare_price(new_item)                          (stretch)       -> str
    check_trends(category, style_tags)               (stretch)       -> str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _chat(prompt: str, temperature: float = 0.7) -> str:
    """Send a single user prompt to the LLM and return the response text."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

# Common words that carry no search signal — stripped from the query before
# keyword scoring so "looking for a vintage tee" scores on {vintage, tee}.
_STOPWORDS = {
    "a", "an", "the", "for", "with", "in", "of", "and", "or", "to", "my", "me",
    "i", "im", "i'm", "looking", "want", "wanting", "need", "find", "some",
    "something", "any", "that", "this", "is", "are", "up", "out", "what",
    "whats", "under", "below", "around", "about", "size", "sized", "please",
}


def _keywords(text: str) -> list[str]:
    """Lowercase, split on non-alphanumerics, drop stopwords and 1-char tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1]


def _size_matches(requested: str, listing_size: str) -> bool:
    """
    Case-insensitive size match. Tokenizes the listing's size string (which can
    look like "S/M", "US 8", "XL (oversized)", "W30 L30") and matches if the
    requested size equals any token, or appears as a substring of the raw size.
    """
    req = requested.strip().lower()
    if not req:
        return True
    raw = listing_size.lower()
    tokens = re.findall(r"[a-z0-9]+", raw)
    return req in tokens or req in raw


def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match
        first). Returns an empty list if nothing matches — never raises.

    Scoring: each query keyword scores +2 when it appears in the title or
    style_tags (the strongest relevance signals) and +1 when it only appears
    elsewhere (description, category, colors, brand). Listings with a score of
    0 are dropped. Ties keep original dataset order (stable sort).
    """
    listings = load_listings()
    keywords = _keywords(description)

    scored: list[tuple[int, dict]] = []
    for item in listings:
        # Hard filters first — price ceiling and size.
        if max_price is not None and item["price"] > max_price:
            continue
        if size is not None and not _size_matches(size, item["size"]):
            continue

        # Strong-signal text (title + style tags) vs. the rest.
        strong = (item["title"] + " " + " ".join(item["style_tags"])).lower()
        weak = " ".join(
            [
                item["description"],
                item["category"],
                " ".join(item["colors"]),
                item["brand"] or "",
            ]
        ).lower()

        score = 0
        for kw in keywords:
            if kw in strong:
                score += 2
            elif kw in weak:
                score += 1

        # With no usable keywords, every filtered item is a valid match.
        if keywords and score == 0:
            continue
        scored.append((score, item))

    # Stable sort, highest score first. Python's sort is stable, so equal
    # scores retain dataset order.
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def _format_wardrobe(wardrobe: dict) -> str:
    """Render wardrobe items as a readable bullet list for the prompt."""
    lines = []
    for w in wardrobe.get("items", []):
        tags = ", ".join(w.get("style_tags", []))
        note = f" ({w['notes']})" if w.get("notes") else ""
        lines.append(f"- {w['name']} [{w['category']}; {tags}]{note}")
    return "\n".join(lines)


def suggest_outfit(
    new_item: dict,
    wardrobe: dict,
    trends: str | None = None,
    style_profile: str | None = None,
) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1-2 complete outfits.

    Args:
        new_item:      A listing dict (the item the user is considering buying).
        wardrobe:      A wardrobe dict with an 'items' key. May be empty.
        trends:        (stretch) Optional trend context from check_trends.
        style_profile: (stretch) Optional saved style-preference text.

    Returns:
        A non-empty string with outfit suggestions. If the wardrobe is empty,
        the LLM gives general styling advice for the item rather than referencing
        specific pieces. If trends/style_profile are None, that context is
        simply omitted from the prompt.
    """
    item_desc = (
        f"{new_item['title']} — ${new_item['price']:.0f}, "
        f"size {new_item['size']}, category {new_item['category']}, "
        f"style: {', '.join(new_item['style_tags'])}, "
        f"colors: {', '.join(new_item['colors'])}."
    )

    context = ""
    if style_profile:
        context += f"\nThe user's saved style preferences: {style_profile}"
    if trends:
        context += f"\nCurrent trend context to lean into: {trends}"

    items = wardrobe.get("items", [])
    if not items:
        prompt = (
            "You are a thrift-savvy personal stylist. A user is considering "
            f"buying this secondhand item:\n{item_desc}\n"
            "They have NOT entered any wardrobe pieces yet. Give general styling "
            "advice for this item: what kinds of pieces pair well with it, what "
            "vibe it suits, and 1-2 example outfit directions they could build. "
            "Keep it warm, specific, and 4-6 sentences."
            f"{context}"
        )
    else:
        prompt = (
            "You are a thrift-savvy personal stylist. A user is considering "
            f"buying this secondhand item:\n{item_desc}\n\n"
            "Here is their current wardrobe:\n"
            f"{_format_wardrobe(wardrobe)}\n\n"
            "Suggest 1-2 complete outfits that pair the new item with specific, "
            "named pieces from their wardrobe. Reference the wardrobe pieces by "
            "name. Explain briefly why each outfit works. Keep it concise."
            f"{context}"
        )

    return _chat(prompt, temperature=0.7)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(
    outfit: str,
    new_item: dict,
    price_assessment: str | None = None,
) -> str:
    """
    Generate a short, shareable outfit caption ("fit card") for the find.

    Args:
        outfit:           The outfit suggestion string from suggest_outfit().
        new_item:         The listing dict for the thrifted item.
        price_assessment: (stretch) Optional price-fairness note to weave in.

    Returns:
        A 2-4 sentence casual social-media caption. If `outfit` is empty or
        whitespace-only, the caption focuses on the item alone (name, price,
        platform) — it never raises.
    """
    item_line = (
        f"{new_item['title']} (${new_item['price']:.0f}, "
        f"from {new_item['platform']})"
    )
    price_line = (
        f"\nWork this price note in naturally: {price_assessment}"
        if price_assessment
        else ""
    )

    if outfit and outfit.strip():
        prompt = (
            "Write a short, casual, authentic social-media caption (2-4 "
            "sentences) for an OOTD post about a thrifted find. It should read "
            "like a real person posting, not a product description.\n"
            f"The find: {item_line}\n"
            f"The outfit: {outfit}\n"
            "Mention the item name, price, and platform naturally (once each). "
            "Capture the outfit vibe in specific terms."
            f"{price_line}"
        )
    else:
        prompt = (
            "Write a short, casual, authentic social-media caption (2-4 "
            "sentences) celebrating a thrifted find. It should read like a real "
            "person posting, not a product description.\n"
            f"The find: {item_line}\n"
            "There is no styled outfit yet — focus on the piece itself, its "
            "vibe, and why it's a great score. Mention the item name, price, "
            "and platform naturally (once each)."
            f"{price_line}"
        )

    # Higher temperature so captions vary across inputs.
    return _chat(prompt, temperature=0.9)


# ── Tool 4: compare_price (stretch) ────────────────────────────────────────────

def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def compare_price(new_item: dict) -> str:
    """
    Estimate whether `new_item`'s price is fair versus comparable listings.

    Loads the comparison set internally via load_listings() (mirroring
    search_listings) and excludes the item from its own comps by id. Comps are
    same-category listings; if any of those share a style_tag with the item,
    the comparison is narrowed to that more relevant subset.

    Returns:
        A string assessing the price (a deal / fair / on the high end) with the
        item's price relative to the comparable average and median. If there
        are no comparables, returns "Insufficient data to assess price."
        (non-fatal — the agent simply omits the price note).
    """
    listings = load_listings()
    same_category = [
        x
        for x in listings
        if x["category"] == new_item["category"] and x["id"] != new_item["id"]
    ]
    if not same_category:
        return "Insufficient data to assess price."

    # Narrow to tag-overlapping comps when possible — more relevant signal.
    item_tags = set(new_item.get("style_tags", []))
    tag_overlap = [x for x in same_category if item_tags & set(x["style_tags"])]
    comps = tag_overlap if tag_overlap else same_category
    basis = "similar-style" if tag_overlap else new_item["category"]

    prices = [x["price"] for x in comps]
    avg = sum(prices) / len(prices)
    med = _median(prices)
    price = new_item["price"]

    # Within 10% of the average reads as fair; beyond that, deal or high.
    if price <= avg * 0.9:
        verdict = "a good deal"
    elif price >= avg * 1.1:
        verdict = "on the high end"
    else:
        verdict = "fairly priced"

    return (
        f"At ${price:.0f}, this is {verdict} compared to {len(comps)} "
        f"{basis} items (average ${avg:.0f}, median ${med:.0f})."
    )


# ── Tool 5: check_trends (stretch) ─────────────────────────────────────────────

# Mock "platform trends" data source — a static dict of trending notes per
# category, as if scraped from Depop/Poshmark. tag_notes lets a matching
# style_tag surface a more specific note.
_TRENDS: dict[str, dict] = {
    "tops": {
        "default": "Boxy, slightly cropped tops and vintage tees are big right now.",
        "tag_notes": {
            "graphic tee": "Bootleg-style band and graphic tees are trending hard.",
            "band tee": "Faded band and bootleg tees are a top search this season.",
            "knitwear": "Chunky, cozy knits are having a moment.",
            "y2k": "Y2K baby tees and mesh layers are everywhere on the feed.",
        },
    },
    "bottoms": {
        "default": "Baggy, low-rise, and wide-leg silhouettes are dominating.",
        "tag_notes": {
            "baggy": "Baggy carpenter and cargo styles are peaking right now.",
            "cargo": "Low-rise cargos are one of the most-searched bottoms.",
            "denim": "Vintage straight-leg and baggy denim are top sellers.",
        },
    },
    "outerwear": {
        "default": "Vintage outerwear with character is in high demand.",
        "tag_notes": {
            "leather": "90s leather bombers are a sought-after grail piece.",
            "denim": "Cropped and customized denim jackets are trending.",
            "athletic": "90s track jackets and windbreakers are back in rotation.",
        },
    },
    "shoes": {
        "default": "Chunky, retro-soled footwear is the dominant trend.",
        "tag_notes": {
            "platform": "Chunky platforms and Mary Janes are a top search.",
            "western": "Suede Chelsea and western boots are trending.",
        },
    },
    "accessories": {
        "default": "Small structured bags and vintage hats are popular adds.",
        "tag_notes": {
            "y2k": "Tiny shoulder bags are a defining Y2K accessory right now.",
        },
    },
}


def check_trends(category: str, style_tags: list[str] | None = None) -> str:
    """
    Surface what's currently popular for an item's category and style_tags,
    using a mock platform-trends data source phrased into a one-line summary.

    Args:
        category:   The selected item's category.
        style_tags: (optional) The item's style tags, used to pick the most
                    relevant trend note.

    Returns:
        A string summarizing current trends relevant to the item. If no trend
        data matches the category, returns "" (non-fatal — suggest_outfit then
        proceeds with trends=None).

    The trend text comes from the static data source; if a Groq key is
    available it is rephrased into one natural sentence, otherwise the raw
    note is returned so the tool still works offline.
    """
    entry = _TRENDS.get(category)
    if not entry:
        return ""

    note = entry["default"]
    for tag in style_tags or []:
        if tag in entry["tag_notes"]:
            note = entry["tag_notes"][tag]
            break

    # Best-effort LLM rephrasing; degrade to the raw note if unavailable.
    try:
        prompt = (
            "Rephrase this fashion-trend note as one upbeat, natural sentence "
            f"a stylist might say. Keep it to one sentence:\n{note}"
        )
        return _chat(prompt, temperature=0.6)
    except Exception:
        return note
