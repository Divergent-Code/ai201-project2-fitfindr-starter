# FitFindr — Agent Context

> This file is intended for AI coding agents. If you are reading this, you know nothing about the project yet. Everything below is derived directly from the source files, comments, documentation, and the course assignment specifications.

---

## Project Overview

FitFindr is a Python-based AI agent that helps users discover secondhand fashion listings and get personalized outfit suggestions based on their existing wardrobe. It is a starter kit for an AI course project (AI 201, Project 2). The agent accepts natural language queries (e.g., "vintage graphic tee under $30, size M"), searches a mock dataset of 40 thrifted listings, suggests outfits that combine the found item with pieces from the user's wardrobe, and generates a shareable "fit card" caption.

The project follows a **planning-first** workflow: students/planning agents are expected to complete `planning.md` before writing any implementation code.

### Deadlines & Estimation
* **Deadline:** Monday, June 15th at 2:59 AM EDT
* **Estimated Time:** ~8–9 hours total

---

## Agent Roles & Task Regulation

To ensure structured execution, development is split between the Planning Agent (**VEGA**) and the Coding Agent (**Hayden**):

* **VEGA (Planning Agent)**: Regulates architecture, design, specification, and validation planning. VEGA must complete all planning tasks before Hayden writes implementation code.
* **Hayden (Coding Agent)**: Regulates implementation, debugging, test suite execution, and validation.

For details on how tasks are distributed across milestones, see [Milestones & Responsibilities](#milestones--responsibilities) below.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.x (uses union syntax `str \| None`, type hints) |
| LLM API | Groq (`groq==0.15.0`) — requires `GROQ_API_KEY` (specifically `llama-3.3-70b-versatile`) |
| Web UI | Gradio (`gradio>=6.9.0`) |
| Env vars | `python-dotenv==1.0.1` |
| Testing | `pytest>=8.0.0` |
| Data | Static JSON files (`listings.json`, `wardrobe_schema.json`) |

---

## Project Structure

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example + empty template
├── utils/
│   └── data_loader.py         # JSON loading helpers (load_listings, get_example_wardrobe, etc.)
├── agent.py                   # Planning loop: orchestrates tools via session dict
├── app.py                     # Gradio web interface
├── tools.py                   # Three agent tools (search_listings, suggest_outfit, create_fit_card)
├── planning.md                # Planning template — must be filled before coding
├── requirements.txt           # Python dependencies
└── README.md                  # Setup and usage instructions
```

---

## Architecture

### Agent Loop (`agent.py`)

The core of the application is `run_agent(query, wardrobe)` in `agent.py`. It executes a sequential planning loop:

1. **Initialize session** — `_new_session()` creates a dict holding all state.
2. **Parse query** — Extract `description`, `size`, `max_price` from natural language.
3. **Search listings** — Call `search_listings()` with parsed params.
4. **Handle no results** — If search returns nothing, set `session["error"]` and return early.
5. **Select top item** — Store the best match in `session["selected_item"]`.
6. **Suggest outfit** — Call `suggest_outfit(selected_item, wardrobe)`.
7. **Create fit card** — Call `create_fit_card(outfit_suggestion, selected_item)`.
8. **Return session** — Caller checks `session["error"]` first.

### Session State

The session dict is the **single source of truth** for one interaction. Keys:

- `"query"` — original user text
- `"parsed"` — extracted filters (description, size, max_price)
- `"search_results"` — list of matching listing dicts
- `"selected_item"` — the chosen listing dict
- `"wardrobe"` — user's wardrobe dict
- `"outfit_suggestion"` — string from `suggest_outfit`
- `"fit_card"` — string from `create_fit_card`
- `"error"` — `None` on success, otherwise a helpful message string

### Tools & Interfaces (`tools.py`)

All three tools are standalone functions meant to be unit-tested in isolation before wiring into the agent loop.

| Tool | Signature | Requirements & Purpose |
|------|-----------|------------------------|
| `search_listings` | `(description: str, size: str \| None = None, max_price: float \| None = None) -> list[dict]` | Keyword + filter search over `data/listings.json`. Must return matching items and handle the case where no matches are found (return empty list, no exception). |
| `suggest_outfit` | `(new_item: dict, wardrobe: dict) -> str` | LLM-based outfit suggestion using wardrobe items. Must handle an empty or minimal wardrobe gracefully. |
| `create_fit_card` | `(outfit: str, new_item: dict) -> str` | LLM-generated social-media caption (short, shareable, different for different inputs). Guard against empty inputs. |

The Groq client is initialized in `_get_groq_client()` and reads `GROQ_API_KEY` from the environment (loaded via `python-dotenv`).

### Web UI (`app.py`)

Gradio Blocks interface with:
- Text input for the user query
- Radio button for wardrobe choice ("Example wardrobe" or "Empty wardrobe")
- Three output text boxes: Top Listing, Outfit Idea, Fit Card
- Example queries pre-loaded for quick testing

`handle_query()` bridges Gradio and `run_agent()`. It is currently unimplemented (returns a placeholder).

---

## Data Formats

### Listing (from `data/listings.json`)

Each of the 40 listings is a dict with:
- `id` (str)
- `title` (str)
- `description` (str)
- `category` (str): tops, bottoms, outerwear, shoes, accessories
- `style_tags` (list[str])
- `size` (str)
- `condition` (str): excellent, good, fair
- `price` (float)
- `colors` (list[str])
- `brand` (str or null)
- `platform` (str): depop, thredUp, poshmark

### Wardrobe (from `data/wardrobe_schema.json`)

A wardrobe dict has an `"items"` key containing a list of item dicts:
- `id` (str)
- `name` (str)
- `category` (str)
- `colors` (list[str])
- `style_tags` (list[str])
- `notes` (str, optional)

The schema file also provides `example_wardrobe` (10 items) and `empty_wardrobe` (0 items).

---

## Build and Run Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key
echo "GROQ_API_KEY=your_key_here" > .env

# 3. Sanity-check data loading
python utils/data_loader.py

# 4. Run CLI test of the agent loop
python agent.py

# 5. Launch the Gradio web UI
python app.py
# Then open the localhost URL shown (usually http://localhost:7860)
```

---

## Testing Strategy

- **Unit-test tools first** — `search_listings`, `suggest_outfit`, and `create_fit_card` should each be tested independently before integration.
- **pytest** — listed in `requirements.txt` for formal test suites.
- **Example Unit Tests** (`tests/test_tools.py`):
    ```python
    from tools import search_listings

    def test_search_returns_results():
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_search_empty_results():
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == [] # empty list, no exception

    def test_search_price_filter():
        results = search_listings("jacket", size=None, max_price=10)
        assert all(item["price"] <= 10 for item in results)
    ```
- **CLI test** — `agent.py` has a `__main__` block that exercises both a happy path and a no-results path.
- **Gradio Examples** — `app.py` includes pre-baked example queries, including a deliberate no-results query ("designer ballgown size XXS under $5").

---

## Code Style Guidelines

- Use **type hints** on all function signatures.
- Write **detailed docstrings** covering args, returns, and behavior on failure.
- Use `TODO` comments in starter code to mark unimplemented sections.
- Follow the **session-dict pattern** for state passing — do not use global state.
- Tools must **fail gracefully** (return empty lists / descriptive strings) rather than raising exceptions for expected error cases.
- The project uses modern Python syntax (`str | None`, list[dict]).

---

## Security Considerations

- The Groq API key must be stored in a `.env` file (ignored by `.gitignore`) and loaded via `python-dotenv`. Never hardcode the key.
- There is no authentication, authorization, or input sanitization beyond what the student implements in the tool functions.
- All data is static JSON — there is no database or network-exposed storage.
- The Gradio interface runs locally by default (`demo.launch()` without `share=True`).

---

## Stretch Features

Stretch features can be completed for extra credit. **VEGA** must update `planning.md` before **Hayden** starts implementing any of these:
- **Price comparison tool**: Add a fourth tool that, given an item, estimates whether the price is fair based on comparable listings in the dataset.
- **Style profile memory**: Allow the agent to remember a user's style preferences across sessions, so they don't have to re-describe their wardrobe every time.
- **Trend awareness**: Add a tool that checks recent posts or tags on a public fashion platform to surface what styles are currently popular in the user's size range.
- **Retry logic with fallback**: If `search_listings` returns no results, automatically retry with loosened constraints (e.g., remove size filter) and inform the user what was adjusted.

---

## Milestones & Responsibilities

The development workflow is broken down into milestones with explicitly regulated roles:

### Milestone 1: Explore Starter Repo and Understand Problem (Responsible: VEGA)
* *Task*: Read listings structure, wardrobe schemas, and loader utilities.
* *Task*: Write a 2-3 sentence conceptual description of FitFindr's interaction and add to the *A Complete Interaction* section of `planning.md`.
* *Checkpoint*: Understand fields and the difference between example and empty wardrobes.

### Milestone 2: Write Spec Before Code (Responsible: VEGA)
* *Task*: Fill out all sections in `planning.md` (tool specs, inputs, outputs, failure modes, planning loop logic, architecture diagram).
* *Task*: Map out the sequential and fallback agent architecture diagram.
* *Task*: Detail the prompting plan and verification plan in `planning.md`.
* *Checkpoint*: Specs, architecture, and AI plan are fully detailed in `planning.md`.

### Milestone 3: Build and Test Each Tool in Isolation (Responsible: Hayden)
* *Task*: Implement functions directly in `tools.py` using specs from `planning.md`.
* *Task*: Implement `search_listings` (filtering by description keywords, size, max price).
* *Task*: Implement `suggest_outfit` with Groq (`llama-3.3-70b-versatile`), handling empty/minimal wardrobes.
* *Task*: Implement `create_fit_card` with Groq, guarding against empty outfit strings.
* *Task*: Write `pytest` unit tests in `tests/test_tools.py` to cover success and failure paths.
* *Checkpoint*: Functions return correct values and handle error cases without raising unexpected exceptions.

### Milestone 4: Wire Up the Planning Loop and State (Responsible: Hayden)
* *Task*: Implement `run_agent()` in `agent.py` to orchestrate session initialization, tool calls, and error handling.
* *Task*: Implement `handle_query()` in `app.py` to connect Gradio to `run_agent()`.
* *Task*: Verify state flow through sequential session keys and conditional branch handling on no results.
* *Checkpoint*: Full query flows through Gradio into agent and tools correctly.

### Milestone 5: Test Every Failure Mode Deliberately (Responsible: Hayden)
* *Task*: Execute direct CLI test commands to verify error behavior (e.g., empty wardrobe, search returning nothing, empty outfit string).
  * *Search failure command*: `python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"`
  * *Empty wardrobe suggest command*: `python -c "from tools import search_listings, suggest_outfit; from utils.data_loader import get_empty_wardrobe; results = search_listings('vintage graphic tee', size=None, max_price=50); print(suggest_outfit(results[0], get_empty_wardrobe()))"`
  * *Empty outfit fit card command*: `python -c "from tools import search_listings, create_fit_card; results = search_listings('vintage graphic tee', size=None, max_price=50); print(create_fit_card('', results[0]))"`
* *Task*: Record or screenshot a handled failure for documentation.
* *Checkpoint*: Failure paths execute gracefully with informative messages.

### Milestone 6: Document and Record (Responsible: Hayden / VEGA joint effort)
* *Task (Hayden)*: Launch web UI on localhost:7860, run end-to-end user checks.
* *Task (VEGA)*: Review specifications, reflect on planning spec vs final code, and write `README.md` covering tool inventory, planning logic, state management, error details, and AI prompting details.
* *Task (Hayden)*: Perform final code checks, clean code comments, and support recording the 3-5 minute demo video.
* *Checkpoint*: Interface runs smoothly, documentation is complete, and the demo video captures all requirements.

---

## Submission Requirements

Submit the following items through the Course Portal:
- [ ] **Link to your forked GitHub repository**
- [ ] **`planning.md`** (completed before coding, updated for stretch features)
- [ ] **`README.md`** (must cover tool inventory, planning loop logic, state management, error handling with examples, spec reflection, and AI usage details)
- [ ] **Demo video** (3–5 minutes showing full flow, state passing, and handled failure modes with narration)

---

## Key Files for Agents

| File | What to know before editing |
|------|----------------------------|
| `planning.md` | Must be completed first; defines tool specs and architecture. |
| `tools.py` | Contains Groq client setup and the three core tool functions. |
| `agent.py` | Contains `_new_session()` and `run_agent()` — the orchestration layer. |
| `app.py` | Contains `handle_query()` — the Gradio-to-agent bridge. |
| `utils/data_loader.py` | Reusable data accessors; paths are resolved relative to the file location. |
