"""Anthropic Claude client for LLM polish pass.

Entry point: polish_report(raw_markdown) -> str

Two-tier auth fallback:
1. ANTHROPIC_API_KEY in .env → uses anthropic SDK directly (production path)
2. No key → shells out to `claude -p` (Claude Code CLI, already authed locally)
3. CLI not found → returns raw markdown unchanged

This means users running Claude Code locally get the polish feature for free
without touching .env. Power users can still set the key for server deployments.
"""

from __future__ import annotations

import logging
import shutil
import subprocess

from app.config import get_settings

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the language polish layer for diamond-mind, an AI-native baseball \
intelligence system. You receive a deterministic Markdown report and must:

1. Sharpen the language — tighten sentences, remove redundancy, improve flow.
2. Add 1–2 sentences of narrative context per game that connect the data \
   to the betting market (e.g. why high bullpen vulnerability matters given \
   today's starter matchup).
3. Flag conflicting signals explicitly — if the data contains tension \
   (e.g. high vulnerability score but elite available arms, or HEATING_UP \
   offense facing a STABLE_STRONG starter), note it in the relevant section.
4. Enforce betting language rules without exception:
   - NEVER use: lock, hammer, guaranteed, free money, must bet, screaming play
   - ONLY use these tiers: Strong Lean / Lean / Pass / Avoid / Need More Info
   - Keep the disclaimer footer unchanged.
5. Do not invent statistics or facts not present in the input report.
6. Return valid Markdown that renders identically structured to the input. \
   Keep all section headers, tables, and bullet lists intact.
"""

_CLI_PROMPT_TEMPLATE = """\
{system}

Please polish the following diamond-mind report. Return only the polished \
Markdown — no preamble, no commentary.

{report}
"""


def _polish_via_sdk(raw_markdown: str, api_key: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Please polish the following diamond-mind report. "
                "Return only the polished Markdown — no preamble.\n\n"
                + raw_markdown
            ),
        }],
    )
    return message.content[0].text


def _polish_via_cli(raw_markdown: str) -> str | None:
    """Shell out to `claude -p` using the local Claude Code auth. Returns None on failure."""
    if not shutil.which("claude"):
        return None
    prompt = _CLI_PROMPT_TEMPLATE.format(system=_SYSTEM_PROMPT, report=raw_markdown)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        log.warning("claude CLI exited %d: %s", result.returncode, result.stderr[:200])
        return None
    except subprocess.TimeoutExpired:
        log.warning("claude CLI timed out after 120s")
        return None
    except Exception as exc:
        log.warning("claude CLI failed: %s", exc)
        return None


def polish_report(raw_markdown: str) -> tuple[str, bool]:
    """Run a Claude polish pass over a deterministic report.

    Returns (markdown, polished) where polished=True means LLM was applied.
    Falls back through: SDK key → CLI → raw.
    """
    settings = get_settings()

    if settings.anthropic_api_key:
        try:
            return _polish_via_sdk(raw_markdown, settings.anthropic_api_key), True
        except Exception as exc:
            log.error("SDK polish failed (%s) — trying CLI fallback.", exc)

    cli_result = _polish_via_cli(raw_markdown)
    if cli_result is not None:
        log.info("Report polished via claude CLI.")
        return cli_result, True

    log.warning("No polish available (no API key, no CLI) — returning raw report.")
    return raw_markdown, False


def is_available() -> bool:
    """True if any polish method is available."""
    return bool(get_settings().anthropic_api_key) or bool(shutil.which("claude"))
