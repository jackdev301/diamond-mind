# Collaboration protocol

Two people (and their AI agents) are building diamond-mind in parallel. This folder is the shared channel — everything async goes through markdown so it lives in git history and can be reviewed in PRs.

## Folder layout

- `tracks/` — one file per track. Scope, current status, what's done, what's next, blockers. Owner updates their own file.
- `interfaces/` — the seams between tracks. Each file describes a contract (DB table, function signature, file path convention) that both sides agree to. **Change requires PR review from the other track.**
- `handoffs/` — dated notes when one side ships something the other depends on. Filename: `YYYY-MM-DD-short-slug.md`. Append-only; don't edit old handoffs, write a new one if something changes.
- `decisions/` — short ADR-style records of cross-cutting choices (tooling, schema decisions, naming). Filename: `NNNN-short-slug.md` (zero-padded sequence). One decision per file.

## Working agreements

1. **Interfaces are the contract.** If you need to change a file in `interfaces/`, open a PR and tag the other track. Don't change it in the same PR as the code that depends on it.
2. **Update your track file when you start or finish a phase.** Other side reads it to know if they're unblocked.
3. **Write a handoff when you ship something the other side will consume.** Examples: "DB schema is live, here's how to query form windows", "betting utility functions merged, here's the import path".
4. **Database is the source of truth.** Track A owns writes; Track B reads. If Track B needs a column that doesn't exist, request it via a handoff or interface PR — don't add it yourself.
5. **No fake data.** If an API key is missing, stub the client and document it. Don't invent values to make the report look complete.
6. **Tests live next to their code.** Each phase should ship with pytest coverage of its pure functions.

## Branch / PR conventions

- Each track works on feature branches off `main`.
- PR titles: `[track-a]` or `[track-b]` prefix so it's obvious who owns the change.
- Anything touching `interfaces/` needs review from the other track.

## When the agents talk to each other

The AI agents on each side read this folder at the start of a session to catch up. If you (the human) want to leave a directed message for the other side's agent, drop it in `handoffs/` with a clear filename — the next session on that track will pick it up.
