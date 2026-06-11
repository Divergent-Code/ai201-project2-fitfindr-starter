# FitFindr 🛍️

FitFindr is an AI agent that turns a natural-language request like
*"vintage graphic tee under $30, size M"* into a complete styling result:
it finds a secondhand listing, compares its price, checks current trends,
suggests outfits built from your wardrobe, and writes a shareable "fit card"
caption — all in one multi-step interaction.

It is built around a **planning loop** that orchestrates five tools, passing
state between them through a single `session` dictionary.

---

## Setup

```bash
pip install -r requirements.txt
echo "GROQ_API_KEY=your_key_here" > .env      # free key at console.groq.com
```

Run it:

```bash
python utils/data_loader.py   # sanity-check the data loads
pytest                        # run the tool unit tests
python agent.py               # CLI walkthrough (happy path, retry, no-results)
python app.py                 # Gradio web UI (http://localhost:7860)
```

The two LLM tools (`suggest_outfit`, `create_fit_card`) require a Groq key.
The data-only tools and the offline path of `check_trends` run without one,
and the LLM-dependent unit tests skip automatically when no key is present.

---

## Tool Inventory

FitFindr uses **3 required tools** plus **2 stretch tools**. Required tools keep
their locked two-argument interfaces; every stretch parameter is appended after
the required positional params and defaults to `None`, so the required calls
still work unchanged.

### 1. `search_listings(description, size=None, max_price=None) -> list[dict]`
- **Purpose:** Keyword + filter search over the 40 listings in
  `data/listings.json`.
- **Inputs:** `description` (str — search keywords), `size` (str | None — e.g.
  `"M"`, matched case-insensitively against listing sizes like `"S/M"`),
  `max_price` (float | None — inclusive ceiling).
- **Returns:** A list of matching **listing dicts** (each with `id`, `title`,
  `description`, `category`, `style_tags`, `size`, `condition`, `price`,
  `colors`, `brand`, `platform`), sorted best-match first. Keywords in the
  title/style_tags score ×2; elsewhere ×1; zero-score items are dropped.
- **On failure / no match:** Returns an empty list `[]` — never raises.

### 2. `suggest_outfit(new_item, wardrobe, trends=None, style_profile=None) -> str`
- **Purpose:** Use the Groq LLM to pair the found item with the user's wardrobe.
- **Inputs:** `new_item` (dict — a listing), `wardrobe` (dict with an `items`
  list), and stretch params `trends` (str | None) and `style_profile`
  (str | None).
- **Returns:** A **string** of 1–2 named outfit suggestions.
- **On failure / no match:** If the wardrobe is empty, the LLM gives general
  styling advice for the item instead of naming pieces; still returns a
  non-empty string. Missing `trends`/`style_profile` are simply omitted.

### 3. `create_fit_card(outfit, new_item, price_assessment=None) -> str`
- **Purpose:** Use the Groq LLM to write a short, shareable OOTD caption.
- **Inputs:** `outfit` (str), `new_item` (dict), stretch param
  `price_assessment` (str | None).
- **Returns:** A **string** caption (2–4 sentences, higher LLM temperature so it
  varies per input), mentioning the item name, price, and platform.
- **On failure / no match:** If `outfit` is empty/whitespace, the caption
  focuses on the item alone — never raises.

### 4. `compare_price(new_item) -> str` *(stretch)*
- **Purpose:** Assess whether the item's price is fair vs. comparable listings.
- **Inputs:** `new_item` (dict). The comparison set is loaded internally via
  `load_listings()` and excludes the item itself by `id`.
- **Returns:** A **string** assessment (a deal / fairly priced / on the high
  end) with the item's price vs. the comparable average and median. Comps are
  same-category listings, narrowed to style-tag overlaps when available.
- **On failure / no match:** Returns `"Insufficient data to assess price."` —
  non-fatal; the agent omits the price note.

### 5. `check_trends(category, style_tags=None) -> str` *(stretch)*
- **Purpose:** Surface what's trending for the item's category/tags.
- **Inputs:** `category` (str), `style_tags` (list[str] | None — picks the most
  relevant trend note).
- **Returns:** A **string** trend summary drawn from a mock platform-trends data
  source (a static trending-tags-per-category dict) and phrased by the LLM.
- **On failure / no match:** Returns `""` for an unknown category — non-fatal;
  `suggest_outfit` proceeds with `trends=None`. (Also degrades to the raw note
  if the LLM is unavailable, so it works offline.)

All three required tools are exercised in a single interaction (see the demo /
the `python agent.py` happy path), along with both stretch tools.

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [`agent.py`](agent.py) runs a **sequential loop
with conditional branches**. It does *not* call every tool unconditionally —
what it does next depends on state it checks between steps:

1. **Load style profile** *(stretch)* — read `data/style_profile.json` into
   `session["style_profile"]` (or `None`).
2. **Parse** the query (regex, no LLM) into `{description, size, max_price}` and
   extract any standing style preferences.
3. **Search** — `search_listings(description, size, max_price)`.
4. **Conditional retry/fallback** *(stretch)* — **this is the loop's main
   branch.** It checks `search_results`:
   - **Non-empty →** continue to step 5.
   - **Empty →** retry in a fixed deterministic order, stopping at the first
     non-empty result: **(a) drop `max_price` → (b) drop `size` → (c) drop
     both**. On success, set `fallback_used=True` and a `warning` naming exactly
     what was relaxed.
   - **Still empty →** set `session["error"]` with an actionable message and
     **return early**, skipping every downstream tool.
5. **Select** the top match → `selected_item`.
6. **Compare price** *(stretch, non-fatal)* → `price_assessment`.
7. **Check trends** *(stretch, non-fatal)* → `trends` (`""` treated as `None`).
8. **Suggest outfit** (passing `trends` + `style_profile`).
9. **Create fit card** (weaving in `price_assessment`).
10. **Save style profile** *(stretch)* — merge new preferences for next time.

**What triggers each decision:** an empty `search_results` triggers the retry
branch; a still-empty result triggers the early-return error branch; the two
stretch tools are wrapped so an exception degrades to `None`/empty instead of
aborting. So a no-results query takes a visibly different path (error, no LLM
calls) than the happy path (all five tools).

---

## State Management

A single **`session` dictionary** is the source of truth for one interaction.
Each step reads the keys it needs and writes its output back, so the *same*
objects flow forward without the user re-entering anything:

```
search_listings → search_results[0] → selected_item → suggest_outfit
suggest_outfit  → outfit_suggestion → create_fit_card
```

| Key | Written by | Notes |
|-----|-----------|-------|
| `query` | init | original user text |
| `parsed` | step 2 | `{description, size, max_price}` |
| `search_results` | step 3/4 | matching listings |
| `selected_item` | step 5 | `search_results[0]` |
| `wardrobe` | init | user's wardrobe |
| `style_profile` | step 1 | *(stretch)* loaded preference text |
| `fallback_used` | step 4 | *(stretch)* True if constraints relaxed |
| `warning` | step 4 | *(stretch)* what was relaxed |
| `price_assessment` | step 6 | *(stretch)* from `compare_price` |
| `trends` | step 7 | *(stretch)* from `check_trends` |
| `outfit_suggestion` | step 8 | from `suggest_outfit` |
| `fit_card` | step 9 | from `create_fit_card` |
| `error` | step 4 | `None` on success; set → other outputs stay `None` |

**Cross-session memory (Style Profile, stretch):** `data/style_profile.json`
holds `{"preferences": "<free-text notes>"}` (git-ignored as user state). On
load, `preferences` populates `session["style_profile"]` and is passed to
`suggest_outfit`. On save, newly detected preference phrases (e.g.
*"I mostly wear baggy jeans"*) are merged **append-if-new** so prior sessions
aren't overwritten. The caller always checks `session["error"]` first.

---

## Error Handling (per tool)

| Tool | Failure mode | Agent response |
|------|--------------|----------------|
| `search_listings` | No results match | Deterministic retry (drop `max_price` → `size` → both); if all fail, set `error` naming the query + what to loosen, return early. |
| `suggest_outfit` | Empty wardrobe | LLM gives general styling advice for the item; still returns a non-empty string. |
| `create_fit_card` | Empty/whitespace outfit | Caption focuses on the item alone (name, price, platform); never raises. |
| `compare_price` *(stretch)* | No comparable items | Returns `"Insufficient data to assess price."`; non-fatal, note omitted. |
| `check_trends` *(stretch)* | Unknown category | Returns `""`; non-fatal, `suggest_outfit` runs with `trends=None`. |

**Concrete example (from testing).** Query: `"designer ballgown size XXS under
$5"`. `search_listings` returns `[]`. The retry drops the $5 ceiling, then the
`XXS` size, then both — all still `[]` (no ballgowns exist in the dataset). The
agent stops before any LLM call and returns:

> No listings matched "designer ballgown". Try raising the price limit, or
> removing the size, or different keywords.

This is specific (names what failed) and actionable (says what to try next).

**Retry example.** Query: `"vintage graphic tee under $10"` returns `[]` (the
cheapest listing is $12). The retry drops `max_price`, finds matches, and sets:

> ℹ️ No exact matches — relaxed the $10 price limit to find these.

---

## Spec Reflection

**One way the spec helped.** The "signature rule" decided up front in
`planning.md` — *required tools keep their two-argument interfaces; every
stretch param is appended and defaults to `None`* — meant the stretch features
(trends, price, style memory) slotted in without breaking the required calls or
the Milestone 5 CLI commands. Writing that rule before coding avoided a painful
mid-build refactor of every call site.

**One divergence and why.** The `planning.md` "Complete Interaction" trace
predicted the top match for *"vintage graphic tee"* would be **"Graphic Tee —
2003 Tour Bootleg Style" ($24)**. The implemented scorer instead ranks the
**"Y2K Baby Tee — Butterfly Print" ($18)** first: both are tagged `graphic tee`
*and* `vintage`, so they tie on keyword score, and the tie breaks to dataset
order. Rather than contort the scorer with an artificial tiebreaker to match the
narrative, I kept the scoring clean — the Y2K tee is a legitimate (and cheaper,
"excellent"-condition) match. The trade-off: the planning narrative no longer
matches the live result, which is fine for a deterministic, explainable scorer.

---

## AI Usage

**Instance 1 — Implementing the five tools.** I directed the AI to implement
`tools.py` from the locked specs in `planning.md`: the keyword-scoring search,
the two Groq-backed generative tools, and the two stretch tools, plus a pytest
suite. **I reviewed/revised:** I had it make `compare_price` and `check_trends`
deterministic where possible (so they're testable offline), added the offline
fallback to `check_trends`, and gated the LLM-dependent tests behind a
`skipif(GROQ_API_KEY)` marker so `pytest` stays green without a key. I verified
the search relevance against the real dataset rather than trusting the docstring.

**Instance 2 — Wiring the planning loop.** I directed the AI to implement
`run_agent()` to the canonical session-key table, including the deterministic
retry order, the non-fatal wrapping of the stretch tools, and the style-profile
load/merge/save. **I reviewed/revised:** I confirmed the retry skips no-op
attempts (e.g. it won't "drop size" when no size was given), checked that the
preference extraction strips its clause out of the search description so
*"I mostly wear baggy jeans"* doesn't pollute the keyword search, and ran the
two-session style-memory flow end-to-end to confirm session 2 reuses session 1's
preferences without re-entry.

---

## Project Layout

```
fitfindr/
├── tools.py            # the 5 tools + Groq client
├── agent.py            # run_agent() planning loop + state + style memory
├── app.py              # Gradio UI (handle_query bridge)
├── tests/test_tools.py # pytest unit tests (success + failure paths)
├── planning.md         # the spec, written before the code
├── data/               # listings.json, wardrobe_schema.json
└── utils/data_loader.py
```
