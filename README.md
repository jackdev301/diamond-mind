# diamond-mind

AI-native baseball intelligence system. Generates a daily MLB pregame report — recent form, bullpen fatigue & vulnerability, weather, betting market verification — served through a React web dashboard with optional Claude polish.

> **Not a pick bot.** A probabilistic decision-support tool that uses cautious language tiers (Strong Lean / Lean / Pass / Avoid / Need More Info). "Lock", "guaranteed", and "hammer" are forbidden by design.

---

## Quick start

```bash
git clone https://github.com/jackdev301/diamond-mind.git
cd diamond-mind

python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env          # fill in keys you have; missing keys degrade gracefully
python scripts/init_db.py     # create tables
python scripts/backfill_history.py --days 30   # seed historical data
python scripts/run_pregame_update.py           # fetch today's schedule + weather

uvicorn app.api.routes:app --reload --port 8000 &   # API at localhost:8000
cd frontend && npm install && npm run dev            # UI at localhost:3000
```

See [docs/SETUP.md](docs/SETUP.md) for the full walkthrough.

---

## What's built

### Data platform (Track A)

| Component | Location | Description |
|-----------|----------|-------------|
| DB models | `app/models/` | 17 SQLAlchemy tables — teams, players, games, game logs, form windows, bullpen, odds, weather, reports |
| Recent form engine | `app/features/recent_form.py` | Season / L20 / L10 / L5 windows for hitters & teams; L10/L5 starts for starters; L20/L10/L5 for relievers. Trend classifier, weighted metric, `build_bullpen_state()` |
| MLB ingestion | `app/ingestion/mlb_stats_api.py` | Schedule, teams, rosters, box scores — idempotent upserts via MLB Stats API (no key needed) |
| Odds ingestion | `app/ingestion/odds_api.py` | The Odds API — moneyline, spread, total. Event-ID matching to MLB game PKs. Skips gracefully without key |
| Weather ingestion | `app/ingestion/weather_api.py` | Open-Meteo (no key needed). Dome detection. Lat/lon for all 30 venues in `venue_coords.py` |
| Daily update | `scripts/run_pregame_update.py` | Full orchestration: schedule → box scores → form windows → bullpen states → weather → odds |
| Backfill | `scripts/backfill_history.py` | Seeds historical game logs for any date range |
| FastAPI | `app/api/routes.py` | Read-only JSON API consumed by the frontend |
| LLM polish | `app/llm/claude_client.py` | Two-tier: Anthropic SDK key → `claude -p` CLI fallback → raw |

### Analysis & output (Track B)

| Component | Location | Description |
|-----------|----------|-------------|
| Bullpen engine | `app/features/bullpen_*.py` | Fatigue scoring, quality rating, vulnerability (0–100) |
| Betting utils | `app/betting/` | Implied probability, edge calc, recommendation tiers |
| Odds/weather clients | `app/ingestion/odds_api.py`, `weather_api.py` | Graceful stubs when keys missing |
| Report generator | `app/reports/daily_report.py` | Deterministic markdown — starters, bullpen, form, odds, weather |
| Obsidian export | `app/obsidian/` | Wiki-linked vault notes per game, bullpen, daily report |
| React frontend | `frontend/` | Next.js — Slate, Game Detail, Report Viewer, Bet Verifier |

---

## API reference

Base URL: `http://localhost:8000` — interactive docs at `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/games?game_date=YYYY-MM-DD` | Games for a date |
| GET | `/games/{id}/bundle?as_of=YYYY-MM-DD` | Full composite — form, starters, bullpen, in one call |
| GET | `/games/{id}/odds` | Latest odds snapshots |
| GET | `/games/{id}/weather` | Latest weather snapshot |
| GET | `/teams` | All teams |
| GET | `/teams/{id}/form?window=l10&as_of=YYYY-MM-DD` | Team form window |
| GET | `/teams/{id}/bullpen?as_of=YYYY-MM-DD` | BullpenState |
| GET | `/players/{id}/form?window=l10&as_of=YYYY-MM-DD` | Hitter form window |
| GET | `/pitchers/{id}/form?window=last_5_starts&as_of=YYYY-MM-DD` | Starter form window |
| POST | `/report/polish` | Claude polish pass → `{markdown, polished, method}` |

---

## Frontend pages

| Page | Route | Description |
|------|-------|-------------|
| Slate | `/` | Date-picker, game cards with bullpen vulnerability colour coding |
| Game Detail | `/game/[id]` | Starters, bullpen intel, weather conditions |
| Daily Report | `/report` | Full markdown report + Polish with Claude (SDK / CLI / Raw badge) |
| Bet Verifier | `/verify` | Client-side implied probability + edge calculator |

---

## Keys & degradation

| Key | Used for | Without it |
|-----|----------|-----------|
| `ANTHROPIC_API_KEY` | SDK polish | Falls back to `claude -p` CLI, then raw report |
| `ODDS_API_KEY` | Live odds | Odds section hidden; everything else works |
| `MLB_STATS_API_BASE` | Game data | Defaults to public statsapi.mlb.com (no key needed) |

Weather uses Open-Meteo — no key required.

---

## Repo layout

```
app/
  config.py          # pydantic-settings, DATABASE_URL, API keys
  contracts.py       # frozen dataclasses — the Track A/B seam
  database.py        # SQLAlchemy engine + session
  models/            # 17 ORM tables
  features/          # recent_form, bullpen_fatigue/quality/vulnerability
  ingestion/         # mlb_stats_api, odds_api, weather_api, venue_coords
  betting/           # edge_calculator, implied_probability
  reports/           # daily_report generator
  obsidian/          # vault_writer, note_templates, link_utils
  llm/               # claude_client (polish)
  api/               # FastAPI routes
scripts/
  init_db.py         # idempotent table creation
  run_pregame_update.py
  backfill_history.py
  collab_server.py   # dev-only inter-agent relay
frontend/            # Next.js app
tests/               # 49 pytest tests + JSON fixtures
docs/
  PROJECT_BRIEF.md   # canonical vision and formulas
  SETUP.md           # full setup walkthrough
  collab/            # cross-track coordination (handoffs, interfaces, decisions)
obsidian_vault/      # exported markdown (content gitignored, folders tracked)
```

---

## Responsible-use note

diamond-mind provides probabilistic baseball analysis and market verification. It does not guarantee outcomes and is not financial advice. The MVP uses rule-based estimates — there is no trained predictive model. Use outputs as one input among many, never as a certainty signal. If you bet, do so responsibly and within your jurisdiction's guidelines.
