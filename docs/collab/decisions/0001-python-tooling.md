# 0001 — Python tooling

**Date:** 2026-05-15
**Status:** Accepted

## Decision

Use **pip + `pyproject.toml`**. Install via:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Dev dependencies (`pytest`, etc.) declared under `[project.optional-dependencies.dev]` in `pyproject.toml`.

## Why

- No new tooling to install. Pip + venv ships with Python.
- `pyproject.toml` is the modern standard; we get editable installs and clean dep declaration without committing to a heavier tool like Poetry, PDM, or uv.
- Lockfile not required for MVP — pin in `pyproject.toml` directly. Revisit if we need reproducible CI builds.

## Implications for both tracks

- Add new runtime deps to `[project.dependencies]` in `pyproject.toml`.
- Add new dev/test deps to `[project.optional-dependencies.dev]`.
- Do not commit `requirements.txt` — single source of truth is `pyproject.toml`.
