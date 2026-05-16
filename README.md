# diamond-mind

AI-native baseball intelligence system. Generates a daily MLB intelligence report from structured data — recent form, bullpen fatigue & quality, betting market verification, Obsidian markdown export.

> **Not a chatbot. Not a pick bot.** A probabilistic decision-support tool. See the responsible-use note at the bottom.

The canonical project vision lives in [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md). Collaboration protocol lives under [`docs/collab/`](docs/collab/).

---

## Status

| Phase | Scope | Status |
|------:|-------|--------|
| 1 | Inspect repo + plan | done |
| 2 | Skeleton, config, contracts, smoke tests | done |
| 3 | Database models | done |
| 4 | Betting utilities | next (Track B) |
| 5 | Recent form engine | done |
| 6 | Bullpen intelligence | Track B |
| 7 | MLB Stats API ingestion | Track A |
| 8 | Odds / weather clients | Track B |
| 9 | Daily report generator | Track B |
| 10 | Obsidian export | Track B |
| 11 | CLI scripts | both |
| 12 | LLM polish (optional) | later |

## What the MVP will support

- Daily Markdown intelligence report covering today's MLB slate.
- Recent form windows: Season / L20 / L10 / L5 for hitters & teams; L10/L5 starts for starters; L20/L10/L5 appearances for relievers.
- Bullpen intelligence: fatigue, overall quality, available quality (after accounting for tired arms), vulnerability.
- Betting market verification: American-odds → implied probability, edge calc, cautious recommendation tiers (Strong Lean / Lean / Pass / Avoid / Need More Info).
- Obsidian vault export for human-readable research notes.

## What is planned later

Streamlit dashboard, FastAPI routes, chatbot follow-up, postgame evaluation grading, logistic regression / elastic-net probability model, XGBoost experiments, historical odds backtesting, richer injury/news ingestion.

## Setup

Python 3.11+ required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill in keys you have; missing keys are OK
pytest                 # smoke tests should pass
```

## Tooling decisions

See [`docs/collab/decisions/`](docs/collab/decisions/). Currently: `pip` + `pyproject.toml`, SQLite for local dev.

## Initializing the database

```bash
python scripts/init_db.py            # idempotent; creates missing tables
python scripts/init_db.py --drop     # destructive: drops everything first
```

17 tables are created — see `app/models/__init__.py` for the full list. The DB path comes from `DATABASE_URL` in `.env` (defaults to `sqlite:///./diamond_mind.db`).

## Running the daily report

*Not yet implemented — lands in Phase 9.* Will be:

```bash
python scripts/run_daily_report.py --date 2026-05-15
```

The script will compute features, verify markets, and write a markdown report to `obsidian_vault/Reports/Daily/YYYY-MM-DD.md`.

## How Obsidian export works

*Lands in Phase 10.* The database is the source of truth; Obsidian is the human-readable memory layer. The exporter writes daily reports, per-game notes, bullpen pages, and bet evaluation notes using wiki-style links (`[[Phillies]]`, `[[Zack Wheeler]]`) so the vault becomes a navigable research graph.

## Interpreting betting outputs

Every bet evaluation includes implied probability, estimated probability, edge, confidence score, supporting/opposing factors, uncertainty flags, and a "what would change the answer" line. Recommendations are tiered as:

- **Strong Lean** — meaningful edge + high evidence quality
- **Lean** — modest edge or moderate confidence
- **Pass** — no edge or mixed signals
- **Avoid** — negative edge or red flags
- **Need More Info** — insufficient data quality

Language like "lock", "guaranteed", or "must bet" is forbidden by design.

## Repo layout (current)

```
app/             # core Python package (config, db, contracts, modules per phase)
docs/
  PROJECT_BRIEF.md           # canonical vision
  collab/                    # cross-track coordination
    tracks/                  # per-owner scope and status
    interfaces/              # contracts between tracks
    handoffs/                # dated async messages
    decisions/               # ADR-style records
scripts/         # CLI entry points
tests/           # pytest suite + fixtures
obsidian_vault/  # exported markdown (gitignored content, folders tracked)
data/            # raw / processed / exports (gitignored content)
```

## Limitations & responsible-use note

diamond-mind provides probabilistic baseball analysis and market verification. It does not guarantee betting outcomes and should not be treated as financial advice. The MVP uses rule-based probability estimates — there is no trained predictive model yet. Use the outputs as one input among many; never as a "lock."

If you bet, do so at amounts you can afford to lose and within whatever responsible-gambling guardrails apply in your jurisdiction.
