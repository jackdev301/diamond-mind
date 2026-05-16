# Diamond Mind — Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Claude Code](https://claude.ai/code) installed and logged in (`claude --version` to verify)

## 1. Clone & install

```bash
git clone https://github.com/jackdev301/diamond-mind.git
cd diamond-mind
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

## 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Required
DATABASE_URL=sqlite:///diamond_mind.db

# Optional — report polishing works without these via Claude Code CLI fallback
ANTHROPIC_API_KEY=sk-ant-...   # direct SDK polish (fastest)
ODDS_API_KEY=...                # live odds from the-odds-api.com
```

> **No API keys?** Report polishing falls back to `claude -p` (your local Claude Code login). Odds display is hidden when no key is set. Everything else works without any keys.

## 3. Initialize the database

```bash
python scripts/init_db.py
```

## 4. Seed historical data

Backfills the last 30 days of box scores and builds form windows:

```bash
python scripts/backfill_history.py
```

## 5. Run the daily pregame update

Fetches today's schedule, probable starters, bullpen state, weather, and odds:

```bash
python scripts/run_pregame_update.py
```

Run this each morning before first pitch (~9–10 AM ET).

## 6. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

API is live at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

## 7. Start the frontend

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000`.

## Pages

| Page | URL | Description |
|------|-----|-------------|
| Slate | `/` | Today's games with bullpen vulnerability scores |
| Game Detail | `/game/[id]` | Starters, bullpen intel, weather conditions |
| Daily Report | `/report` | Full markdown report with optional Claude polish |
| Bet Verifier | `/verify` | Implied probability + edge calculator |

## Report polishing — how it works

The "Polish with Claude" button on the Report page uses a three-tier fallback:

1. **`ANTHROPIC_API_KEY` set** → calls Anthropic SDK directly (fastest, no CLI needed)
2. **No key, Claude Code installed** → shells out to `claude -p` using your local login
3. **Neither** → returns raw markdown unchanged

The badge next to the button shows which method was used: `AI-Polished (SDK)`, `AI-Polished (CLI)`, or `Raw`.

## Collab server (dev only)

If running two Claude Code agents in parallel for development:

```bash
python -m uvicorn scripts.collab_server:app --host 0.0.0.0 --port 8765
python scripts/collab_poll.py   # in a separate terminal
```
