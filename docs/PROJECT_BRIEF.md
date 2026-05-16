# diamond-mind — Project Brief

> This document is the canonical project vision, captured verbatim from Arnav's initial briefing. Any agent working on this repo should treat this as the source of truth for *what* we are building and *how*. If something here conflicts with code or other docs, this brief wins until explicitly revised.

---

## Project name

**diamond-mind**

## Vision

diamond-mind is an AI-native baseball intelligence system.

It is **NOT** primarily a chatbot.
It is **NOT** a reckless sports betting bot.
It is **NOT** just a wrapper around APIs.

The MVP is a **daily MLB intelligence report generator** that uses structured data, deterministic feature calculations, bullpen intelligence, betting market verification, and Obsidian markdown export.

The long-term goal is a continuously updating baseball reasoning system that can:

- generate daily MLB slate reports
- analyze team/player recent form
- model bullpen fatigue, quality, and vulnerability
- verify bets probabilistically
- explain supporting and opposing evidence
- export research notes to Obsidian
- later support a UI/dashboard and chatbot follow-up interface

## Core design principle

Build deterministic, testable data and scoring logic first. Use the LLM only after the system has structured facts and computed features. The LLM should interpret evidence, critique uncertainty, and write reports. It should not invent stats, fabricate API results, or be the source of truth.

## What to build NOW for MVP

Backend / report pipeline first. The MVP should include:

1. Python project skeleton
2. Config and .env setup
3. Database schema/models
4. MLB Stats API ingestion foundation
5. Recent form calculation engine
6. Bullpen intelligence engine
7. Betting utility functions
8. Odds/weather client interfaces
9. Daily report generator
10. Obsidian markdown export
11. CLI scripts
12. Basic tests

**Main MVP output:** a daily Markdown MLB intelligence report generated from structured data.

## DO NOT build yet

- Full polished web UI
- Live betting
- Parlay optimizer
- Autonomous bet placement
- Black-box ML prediction model
- Paid-API-only dependencies
- Faked completed integrations
- Invented API responses

Use clean interfaces and stubs where API keys or unavailable services are required.

## Design for later

The first MVP is backend / report-pipeline focused, but the repo should be structured so a UI can be added later. Later versions should support:

- Streamlit dashboard
- FastAPI routes
- chatbot follow-up interface
- report viewer
- game-by-game cards
- bullpen dashboard
- bet verification input form
- Obsidian note browser/export controls
- postgame evaluation dashboard
- logistic regression / elastic-net probability model
- XGBoost/LightGBM experiments
- richer injury/news ingestion
- historical odds/backtesting framework

## Recommended tech stack

- **Language:** Python
- **Backend/API:** FastAPI
- **Database:** SQLite for local MVP, structured so PostgreSQL can be swapped in later
- **Data jobs:** CLI scripts first; APScheduler later if needed
- **Data analysis:** pandas, numpy
- **ML (later):** scikit-learn logistic regression / elastic net; XGBoost or LightGBM later
- **LLM (later):** Claude API for report polishing, risk critique, NL explanations
- **Frontend (later):** Streamlit first, possibly Next.js later
- **Obsidian:** local markdown vault writer
- **Testing:** pytest
- **Config:** .env + pydantic-settings or a clean config module

## Data sources

MVP sources:

- **MLB Stats API** — schedule, teams, players, probable pitchers, game status, box scores, play-by-play, pitcher usage
- **Baseball Savant / pybaseball** — later, advanced Statcast metrics
- **The Odds API** — odds, if API key available
- **Open-Meteo or OpenWeather** — weather
- **RotoWire bullpen usage page** — reference/check only, not primary source of truth
- **Obsidian** — local markdown export

The database is the source of truth. Obsidian is the human-readable memory/research layer.

## Daily report structure

The generated daily report should eventually include:

1. Slate Overview
2. Game-by-Game Intelligence
3. Recent Form Dashboard: Season / L20 / L10 / L5
4. Bullpen Intelligence Dashboard
5. Matchup Edges
6. Betting Market Verification
7. Watchlist
8. Uncertainty + Data Quality Warnings
9. Postgame Evaluation Placeholder

## Recent form model

diamond-mind evaluates all major player/team analysis using a season baseline plus recent-form windows.

**Hitters and teams:** Season / L20 / L10 / L5
**Starting pitchers:** Season / Last 10 starts / Last 5 starts
**Relievers:** Season / Last 20 appearances / Last 10 appearances / Last 5 appearances

Compare recent form to season baseline and assign trend labels:

- Heating Up
- Cooling Off
- Stable Strong
- Stable Weak
- Volatile
- Regression Risk
- Small Sample Warning

Do not blindly overweight recent form. L5 is a signal, not a conclusion.

**MVP weighting:**

- Season baseline: 50%
- L20: 25%
- L10: 15%
- L5: 10%

**Time-sensitive / player-prop style (later):**

- Season baseline: 40%
- L20: 30%
- L10: 20%
- L5: 10%

Small sample warnings are required.

## Bullpen intelligence model

This is a signature feature. Do not only look at bullpen usage — also evaluate quality.

The bullpen module must calculate:

1. **Bullpen Fatigue Score** — how tired the bullpen is based on recent usage
2. **Overall Bullpen Quality Score** — how good across season-long and recent performance
3. **Available Bullpen Quality Score** — how good today after accounting for tired/limited/unavailable relievers
4. **Bullpen Vulnerability Score** — combines fatigue and available quality for today's game risk

**Key insight:** a taxed elite bullpen ≠ a taxed weak bullpen. A fresh bad bullpen is not automatically safe. The system must explain when a tired bullpen is still manageable because available arms are strong, and when moderate fatigue is dangerous because available arms are poor.

### MVP fatigue formula

```
score = 0

# Team workload
+10 if bullpen IP yesterday >= 3
+20 if bullpen IP yesterday >= 4
+30 if bullpen IP yesterday >= 5

# Pitch workload
+10 if bullpen pitches yesterday >= 50
+20 if bullpen pitches yesterday >= 70

# Reliever count
+5  if relievers used yesterday >= 4
+10 if relievers used yesterday >= 5

# Rest patterns
+8 per back-to-back reliever, capped at 24
+10 per 3-in-4 reliever, capped at 20

# Key arms
+10 if closer pitched yesterday
+8 per setup/high-leverage arm pitched yesterday, capped at 16

final = min(score, 100)
```

### MVP vulnerability formula

```
Bullpen Vulnerability =
    0.55 * Fatigue Score
  + 0.45 * (100 - Available Bullpen Quality)
```

**Later adjustments:**

- starter short-leash risk
- opponent L10 offensive pressure
- park/weather run environment
- doubleheader / extra-inning context

### Bullpen report output should include

- Fatigue Score
- Overall Bullpen Quality
- Available Bullpen Quality
- Vulnerability Score
- Likely unavailable relievers
- Limited relievers
- Best available arms
- Weak available arms
- Betting implications

## Betting verification model

diamond-mind is framed as a **betting verification and probabilistic decision-support system**, not a pick bot.

**Forbidden language:** lock, guaranteed, free money, must bet, hammer.

**Cautious recommendation tiers:**

- Strong Lean
- Lean
- Pass
- Avoid
- Need More Info

Each bet evaluation should include:

- Market
- Selection
- Current Odds
- Implied Probability
- Estimated Probability
- Edge
- Confidence Score
- Evidence Quality Score
- Recommendation
- Supporting Factors
- Opposing Factors
- Uncertainty Flags
- What would change the answer

### American odds formulas

```
If odds < 0:  implied_probability = abs(odds) / (abs(odds) + 100)
If odds > 0:  implied_probability = 100 / (odds + 100)
edge = model_probability - implied_probability
```

For MVP, estimated probability can be rule-based. **Do not pretend a fully trained predictive model exists yet.**

### Market logic

- Starting pitcher edge → more relevant to **First 5** markets.
- Bullpen vulnerability → more relevant to **full-game** markets, team totals, late-game/live context.
- Strong starter edge + weak bullpen → prefer **F5** over full-game.
- High bullpen vulnerability + strong starters → **full-game over** may be more relevant than F5 over.

## Obsidian integration

Obsidian is the human-readable memory and research layer.

```
obsidian_vault/Reports/Daily/YYYY-MM-DD.md
obsidian_vault/Games/YYYY-MM-DD_AWAY_vs_HOME.md
obsidian_vault/Teams/Team_Name.md
obsidian_vault/Players/Player_Name.md
obsidian_vault/Bullpens/Team_Name_Bullpen.md
obsidian_vault/Bets/YYYY-MM-DD_Bet_Name.md
obsidian_vault/Model_Evals/YYYY-MM-DD.md
```

Use wiki-style links: `[[Phillies]]`, `[[Mets]]`, `[[Zack Wheeler]]`, `[[Mets Bullpen]]`, `[[2026-05-15 PHI vs NYM]]`.

The database remains the source of truth. Obsidian exports are readable summaries and memory notes.

## Agent architecture

Modular pipeline. Not everything has to be an LLM agent. Python/data agents do factual work. LLM agents (later) do reasoning, critique, and writing.

**MVP agents / modules:**

1. Data Ingestion Agent
2. Feature Engineering Agent
3. Bullpen Intelligence Agent
4. Game Analysis Agent
5. Market Verification Agent
6. Risk / Uncertainty Agent
7. Report Writer Agent
8. Obsidian Export Agent
9. Postgame Evaluation Agent

**Morning pipeline:**

```
Fetch today's slate
→ update player/team/game data
→ calculate Season/L20/L10/L5 form
→ calculate bullpen fatigue, quality, available quality, vulnerability
→ fetch odds and weather when keys are available
→ analyze each game
→ verify market edges
→ run uncertainty critique
→ generate daily report
→ export to Obsidian
```

**Postgame pipeline:**

```
Fetch final scores and box scores
→ update game logs and bullpen usage
→ grade watchlist/bet evaluations
→ review whether reasoning was valid
→ update Obsidian notes
```

## Database schema

Implement clean models/tables for at least:

**Identity:** teams, players, games
**Performance:** player_game_logs, pitcher_game_logs, team_game_logs
**Derived form:** player_form_windows, pitcher_form_windows, team_form_windows
**Bullpen:** reliever_usage, bullpen_fatigue
**Market/context:** odds_snapshots, weather_snapshots
**Reasoning/eval:** bet_evaluations, model_runs
**Memory:** obsidian_exports

Don't overcomplicate, but represent these concepts.

## Recommended repo structure

```
diamond-mind/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   │
│   ├── api/
│   │   ├── routes_reports.py
│   │   ├── routes_games.py
│   │   ├── routes_bets.py
│   │   └── routes_chat.py
│   │
│   ├── ingestion/
│   │   ├── mlb_stats_api.py
│   │   ├── statcast.py
│   │   ├── odds_api.py
│   │   ├── weather_api.py
│   │   └── rotowire_reference.py
│   │
│   ├── models/
│   │   ├── entities.py
│   │   ├── games.py
│   │   ├── players.py
│   │   ├── bullpen.py
│   │   ├── odds.py
│   │   └── reports.py
│   │
│   ├── features/
│   │   ├── recent_form.py
│   │   ├── bullpen_fatigue.py
│   │   ├── bullpen_quality.py
│   │   ├── market_features.py
│   │   └── matchup_features.py
│   │
│   ├── agents/
│   │   ├── data_ingestion_agent.py
│   │   ├── feature_engineering_agent.py
│   │   ├── bullpen_intelligence_agent.py
│   │   ├── game_analysis_agent.py
│   │   ├── market_verification_agent.py
│   │   ├── risk_uncertainty_agent.py
│   │   ├── report_writer_agent.py
│   │   ├── obsidian_export_agent.py
│   │   └── postgame_evaluation_agent.py
│   │
│   ├── reports/
│   │   ├── daily_report.py
│   │   ├── game_report.py
│   │   └── markdown_templates.py
│   │
│   ├── obsidian/
│   │   ├── vault_writer.py
│   │   ├── note_templates.py
│   │   └── link_utils.py
│   │
│   ├── betting/
│   │   ├── implied_probability.py
│   │   ├── edge_calculator.py
│   │   ├── recommendation_rules.py
│   │   └── grading.py
│   │
│   ├── evaluation/
│   │   ├── postgame_grader.py
│   │   ├── calibration.py
│   │   └── metrics.py
│   │
│   └── llm/
│       ├── claude_client.py
│       ├── prompts.py
│       └── schemas.py
│
├── scripts/
│   ├── init_db.py
│   ├── run_daily_report.py
│   ├── run_pregame_update.py
│   ├── run_postgame_update.py
│   └── backfill_history.py
│
├── streamlit_app/
│   └── dashboard.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── exports/
│
├── obsidian_vault/
│   ├── Reports/
│   ├── Games/
│   ├── Teams/
│   ├── Players/
│   ├── Bullpens/
│   ├── Bets/
│   └── Model_Evals/
│
└── tests/
    ├── test_recent_form.py
    ├── test_bullpen_scores.py
    ├── test_implied_probability.py
    ├── test_edge_calculator.py
    └── test_report_generation.py
```

## Build phases

Work in phases — do not build everything in one pass.

1. **Phase 1** — Inspect repo, summarize state, create implementation plan.
2. **Phase 2** — Project skeleton, config, .env.example, README draft, test setup.
3. **Phase 3** — Database models and initialization.
4. **Phase 4** — Betting utility functions: American odds → implied probability, edge calculator, recommendation tiers, tests.
5. **Phase 5** — Recent form calculations: hitters/team L20/L10/L5, starters L10/L5, relievers L20/L10/L5, trend labels, small sample warnings, tests.
6. **Phase 6** — Bullpen intelligence: fatigue, quality, available quality, vulnerability, availability labels, explanation builder, tests.
7. **Phase 7** — MLB Stats API ingestion foundation: schedule, teams, players, games, box score/pitcher usage extraction where possible.
8. **Phase 8** — Odds/weather client structure: use API keys from .env, fail gracefully when missing, do not fake data.
9. **Phase 9** — Daily report generator: deterministic/template-based first, generate markdown from computed data.
10. **Phase 10** — Obsidian export: write daily report and related notes, use wiki links, track exported files.
11. **Phase 11** — CLI scripts: init_db.py, run_daily_report.py, run_pregame_update.py, run_postgame_update.py, backfill_history.py.
12. **Phase 12** — Only after structured pipeline works, optional LLM report polishing / risk critique.

## Testing requirements

Write tests for:

- implied probability conversion
- edge calculation
- recommendation tier logic
- recent form window calculations
- bullpen fatigue scoring
- bullpen vulnerability scoring
- Obsidian path generation
- markdown report generation

## Claude behavior rules

**Before coding:**

1. Inspect the repo.
2. Summarize what exists.
3. Identify gaps.
4. Propose a phase-by-phase implementation plan.
5. Start with the smallest useful milestone.

**While coding:**

- Prefer clean, testable functions.
- Avoid hardcoding fake stats.
- Use typed functions where practical.
- Use clear interfaces around external APIs.
- Fail gracefully when API keys are missing.
- Keep modules separated by responsibility.
- Do not make the LLM the source of truth.

**After coding each phase:**

1. Run tests if possible.
2. Summarize changed files.
3. Explain what works.
4. Explain what remains stubbed or incomplete.
5. Suggest the next phase.

## README requirements

Create or update a README explaining:

- what diamond-mind is
- what the MVP currently supports
- what is planned later
- how to set up the environment
- how to initialize the database
- how to run the daily report
- how Obsidian export works
- how betting outputs should be interpreted
- limitations and responsible-use note

**Responsible-use note:**

> diamond-mind provides probabilistic baseball analysis and market verification. It does not guarantee betting outcomes and should not be treated as financial advice.

## Development workflow note

Arnav has gstack skills installed in Claude Code. They are **development workflow tools only** — do not add gstack as a dependency or runtime component of this repo. Before implementation, `/office-hours` and `/plan-eng-review` may be used to challenge scope and architecture. After major milestones, `/review` and `/qa`. Use `/document-generate` when creating documentation.
