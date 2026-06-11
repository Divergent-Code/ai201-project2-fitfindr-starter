"""
tests/test_tools.py

Unit tests for the FitFindr tools, covering both success and failure paths.

The two data-only tools (search_listings, compare_price) and the offline
fallback path of check_trends run with no network. The generative tools
(suggest_outfit, create_fit_card, and the LLM-phrased path of check_trends)
require a live Groq key, so those tests are skipped automatically when
GROQ_API_KEY is not set.

Run from the project root:
    pytest
"""

import os

import pytest

from tools import (
    search_listings,
    suggest_outfit,
    create_fit_card,
    compare_price,
    check_trends,
)
from utils.data_loader import (
    load_listings,
    get_example_wardrobe,
    get_empty_wardrobe,
)

# Generative tests only run when a real key is available.
requires_groq = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM tests.",
)


# ── search_listings ─────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(isinstance(item, dict) for item in results)


def test_search_empty_results():
    # Nonexistent item with impossible filters -> empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=42)
    assert all(item["price"] <= 42 for item in results)


def test_search_size_filter_case_insensitive():
    # "m" should match listings whose size token includes M (e.g. "M", "S/M").
    results = search_listings("tee", size="m", max_price=None)
    assert len(results) > 0
    assert all("m" in item["size"].lower() for item in results)


def test_search_under_10_is_empty_then_present_without_ceiling():
    # The cheapest listing is $12, so an under-$10 tee search returns nothing,
    # but dropping the ceiling surfaces matches (drives the retry stretch path).
    assert search_listings("vintage graphic tee", max_price=10) == []
    assert len(search_listings("vintage graphic tee")) > 0


def test_search_sorted_best_match_first():
    results = search_listings("vintage graphic tee")
    titles = [r["title"] for r in results]
    # A literal graphic tee should rank above an unrelated vintage item.
    assert any("Graphic Tee" in t or "Band Tee" in t for t in titles[:3])


# ── compare_price (stretch) ──────────────────────────────────────────────────

def test_compare_price_returns_assessment():
    item = next(x for x in load_listings() if x["id"] == "lst_006")
    result = compare_price(item)
    assert isinstance(result, str)
    assert "$" in result
    # Must reflect one of the three verdicts.
    assert any(
        phrase in result
        for phrase in ("good deal", "fairly priced", "on the high end")
    )


def test_compare_price_excludes_self():
    # Even though we compare against the dataset, the item never compares to
    # itself — a unique fabricated category yields no comps.
    item = {
        "id": "lst_006",
        "category": "tops",
        "style_tags": ["graphic tee"],
        "price": 24.0,
    }
    result = compare_price(item)
    # lst_006's own id is excluded; other tops still provide comps.
    assert "Insufficient" not in result


def test_compare_price_insufficient_data():
    fake = {
        "id": "lst_999",
        "category": "spacesuits",  # category with no comparables
        "style_tags": ["nasa"],
        "price": 999.0,
    }
    assert compare_price(fake) == "Insufficient data to assess price."


# ── check_trends (stretch) ───────────────────────────────────────────────────

def test_check_trends_unknown_category_empty():
    assert check_trends("spacesuits", ["nasa"]) == ""


def test_check_trends_known_category_nonempty():
    # Works offline: falls back to the raw trend note if no LLM key.
    result = check_trends("tops", ["graphic tee"])
    assert isinstance(result, str)
    assert result != ""


# ── suggest_outfit (LLM) ─────────────────────────────────────────────────────

@requires_groq
def test_suggest_outfit_with_wardrobe():
    item = load_listings()[5]  # lst_006, graphic tee
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""


@requires_groq
def test_suggest_outfit_empty_wardrobe_graceful():
    item = load_listings()[5]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip() != ""  # general advice, not an empty/error string


# ── create_fit_card (LLM) ────────────────────────────────────────────────────

@requires_groq
def test_create_fit_card_normal():
    item = load_listings()[5]
    result = create_fit_card("Pair the tee with baggy jeans and sneakers.", item)
    assert isinstance(result, str)
    assert result.strip() != ""


@requires_groq
def test_create_fit_card_empty_outfit_graceful():
    item = load_listings()[5]
    result = create_fit_card("", item)  # empty outfit -> item-focused caption
    assert isinstance(result, str)
    assert result.strip() != ""
