"""Anthropic Claude client for LLM polish pass.

Entry point: polish_report(raw_markdown) -> str

Takes the deterministic report from Track B's generate_daily_report(),
asks Claude to sharpen language, add narrative context, flag conflicting
signals, and enforce the project's betting language rules.

Stubs gracefully when ANTHROPIC_API_KEY is missing — returns the raw
report unchanged rather than crashing.
"""

from __future__ import annotations

import logging

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


def polish_report(raw_markdown: str) -> str:
    """Run a Claude polish pass over a deterministic report.

    Returns the polished markdown, or the raw input if the API key is
    missing or the call fails.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.warning("ANTHROPIC_API_KEY not set — returning raw report.")
        return raw_markdown

    try:
        import anthropic  # lazy import so the package isn't required to run tests
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=8192,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Please polish the following diamond-mind report. "
                        "Return only the polished Markdown — no preamble.\n\n"
                        + raw_markdown
                    ),
                }
            ],
        )
        return message.content[0].text
    except Exception as exc:
        log.error("LLM polish failed (%s) — returning raw report.", exc)
        return raw_markdown


def is_available() -> bool:
    return bool(get_settings().anthropic_api_key)
