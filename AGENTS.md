# FitFindr — Agent Context

> This file is intended for AI coding agents. If you are reading this, you know nothing about the project yet. Everything below is derived directly from the source files, comments, and documentation.

---

## Project Overview

FitFindr is a Python-based AI agent that helps users discover secondhand fashion listings and get personalized outfit suggestions based on their existing wardrobe. It is a starter kit for an AI course project (AI 201, Project 2). The agent accepts natural language queries (e.g., "vintage graphic tee under $30, size M"), searches a mock dataset of 40 thrifted listings, suggests outfits that combine the found item with pieces from the user's wardrobe, and generates a shareable "fit card" caption.

The project follows a **planning-first** workflow: students are expected to complete `planning.md` before writing any implementation code.

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.x (uses union syntax `str \| None`, type hints) |
| LLM API | Groq (`groq==0.15.0`) — requires `GROQ_API_KEY` |
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

### Tools (`tools.py`)

All three tools are standalone functions meant to be unit-tested in isolation before wiring into the agent loop.

| Tool | Signature | Purpose |
|------|-----------|---------|
| `search_listings` | `(description, size=None, max_price=None) -> list[dict]` | Keyword + filter search over `data/listings.json` |
| `suggest_outfit` | `(new_item: dict, wardrobe: dict) -> str` | LLM-based outfit suggestion using wardrobe items |
| `create_fit_card` | `(outfit: str, new_item: dict) -> str` | LLM-generated social-media caption |

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
- **CLI test** — `agent.py` has a `__main__` block that exercises both a happy path and a no-results path.
- **pytest** — listed in `requirements.txt` for formal test suites.
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

## Development Workflow

1. Read `README.md` for setup instructions.
2. Fill out `planning.md` before writing code.
3. Implement and test each tool in `tools.py` individually.
4. Wire tools into the planning loop in `agent.py`.
5. Connect the loop to the Gradio UI in `app.py` via `handle_query()`.
6. Verify happy path and error paths (no results, empty wardrobe, etc.).

---

## Key Files for Agents

| File | What to know before editing |
|------|----------------------------|
| `planning.md` | Must be completed first; defines tool specs and architecture. |
| `tools.py` | Contains Groq client setup and the three core tool functions. |
| `agent.py` | Contains `_new_session()` and `run_agent()` — the orchestration layer. |
| `app.py` | Contains `handle_query()` — the Gradio-to-agent bridge. |
| `utils/data_loader.py` | Reusable data accessors; paths are resolved relative to the file location. |
