# diamond-mind — agent bootstrap

You are an AI agent (Claude, or otherwise) working on **diamond-mind**, an AI-native baseball intelligence system. Two humans collaborate on this repo: **Arnav** (Track A — data platform) and **Jack** (Track B — analysis & output). Each has their own agent. This file tells your agent how to get oriented at the start of every session.

## Read these in order before doing anything

1. **`docs/PROJECT_BRIEF.md`** — the full project vision, MVP scope, build phases, formulas (bullpen fatigue, vulnerability, betting math), data contracts, and behavior rules. This is the source of truth for *what* we're building and *how*.
2. **`docs/collab/README.md`** — collaboration protocol. How the two tracks coordinate via markdown.
3. **Your track file:**
   - If you're working for Arnav → `docs/collab/tracks/track-a-data.md`
   - If you're working for Jack → `docs/collab/tracks/track-b-analysis.md`
4. **`docs/collab/interfaces/`** — every file. These are contracts between the tracks. Re-read on every session; they evolve.
5. **`docs/collab/handoffs/`** — newest files first. Anything addressed to your track that you haven't acted on yet.
6. **`docs/collab/decisions/`** — durable cross-cutting decisions (tooling, schema choices, naming). Skim once; don't relitigate.

## Hard rules (from PROJECT_BRIEF.md, surfaced here so you can't miss them)

- **Database is the source of truth.** Obsidian is the human-readable memory layer, not canonical storage.
- **Deterministic logic first, LLM second.** The LLM interprets and writes; it never invents stats or replaces computed features.
- **No fake data.** If an API key is missing, stub the client and document it. Never fabricate values to make a report look complete.
- **Betting language: verification, not picks.** Use "Strong Lean / Lean / Pass / Avoid / Need More Info". Never "lock", "guaranteed", "hammer", "free money", "must bet".
- **Stay in your track.** Don't edit files outside your track's scope without a handoff. Track A owns `app/ingestion/`, `app/models/`, `app/features/recent_form.py`. Track B owns `app/betting/`, `app/features/bullpen_*.py`, `app/reports/`, `app/obsidian/`.
- **Interfaces require PR review from the other track.** If you need to change `docs/collab/interfaces/*`, that's a separate PR, tagged for the other side.

## What to do when you finish a unit of work

1. Update your track file's status checklist.
2. If another track depends on what you just shipped, write a handoff: `docs/collab/handoffs/YYYY-MM-DD-short-slug.md`.
3. Run tests. Report what passes and what's stubbed.
4. Don't push or merge without the human asking.

## What gstack / other skills are for

The repo owner (Arnav) has gstack skills installed in Claude Code. They are **dev workflow tools only** — never add gstack as a runtime dependency. Skills like `/office-hours`, `/plan-eng-review`, `/review`, `/qa`, `/document-generate` are useful at phase boundaries. Don't invoke them unprompted.
