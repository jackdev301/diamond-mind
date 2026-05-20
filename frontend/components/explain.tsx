"use client";

import React, { useEffect, useId, useRef, useState } from "react";

/**
 * Canonical quant glossary. Copy is verbatim from spec.md Step 6 and is
 * verification-only language (no overclaiming, no certainty wording). This map
 * is the single source of truth shared by ExplainTooltip and GlossaryPanel.
 */
export const GLOSSARY: Record<string, string> = {
  "shin-devig":
    "Shin (1992) devig removes the bookmaker's overround by modeling a proportion of insider bettors. Produces less-biased implied probabilities than proportional devig, especially on longshots.",
  "bayesian-shrinkage":
    "The model probability is blended toward the market's implied probability in log-odds space, weighted by evidence quality. A model that disagrees with a liquid market by 8+ points is more likely wrong than right.",
  "p-plus-ev":
    "Probability that the estimated edge is greater than zero, given uncertainty in the model's win probability. A figure near 50% means the edge is within noise; above 65% is meaningful signal.",
  "uncertainty-kelly":
    "Kelly fraction derived from edge uncertainty rather than hardcoded. When the model's estimate is noisy, the optimal bet shrinks — the Kelly criterion self-throttles on low-confidence edges.",
  "expected-log-growth":
    "Expected change in log(bankroll) per bet. Positive values indicate long-run growth; negative indicates shrinkage. The Kelly criterion maximizes this quantity.",
  "doubling-time":
    "Estimated number of bets at this edge and stake size to double a bankroll. Displayed as '∞' or 'N/A' when the edge is zero or negative.",
  tiers:
    "Model recommendation tiers are STRONG LEAN (meaningful edge, high confidence), LEAN (moderate edge), PASS (no clear edge), AVOID (edge against). These reflect model signal, not certain outcomes. Never represent certainty.",
  fip:
    "Fielding Independent Pitching — ERA-like stat covering only strikeouts, walks, and home runs (outcomes the pitcher controls directly). Lower is better.",
  xfip:
    "xFIP normalizes FIP by replacing actual home runs with expected home runs based on fly ball rate. Regresses out HR variance.",
  "vig-overround":
    "The bookmaker's built-in margin. A two-sided market with overround > 100% means the implied probabilities sum above 1.0 — the excess is the book's edge.",
  "brier-score":
    "Mean squared error of probability forecasts: (1/n)·Σ(predicted − outcome)². Lower is better. A score of 0.25 is equivalent to always predicting 50%.",
  calibration:
    "A model is calibrated when its stated probabilities match observed frequencies — games predicted at 65% should win roughly 65% of the time.",
};

/** Human-readable label for a glossary key (e.g. "shin-devig" → "Shin Devig"). */
export function termLabel(term: string): string {
  return term
    .split("-")
    .map((w) => (w === "fip" || w === "xfip" ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

type Props = {
  term: string;
  children?: React.ReactNode;
};

/**
 * Inline progressive-disclosure affordance. Renders a keyboard-focusable
 * trigger (the supplied children, or a default ⓘ glyph) that reveals a
 * popover with the glossary copy on hover/focus. Closes on click-outside,
 * blur, or Escape. If `term` is unknown, renders the children with no popover.
 */
export function ExplainTooltip({ term, children }: Props) {
  const copy = GLOSSARY[term];
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLSpanElement>(null);
  const popId = useId();

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!copy) {
    return <>{children}</>;
  }

  return (
    <span
      ref={wrapRef}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: "4px" }}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      {children}
      <button
        type="button"
        className="explain-trigger"
        aria-label={`${termLabel(term)} — explanation`}
        aria-expanded={open}
        aria-describedby={open ? popId : undefined}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        style={{ fontSize: "11px", lineHeight: 1 }}
      >
        ⓘ
      </button>
      {open && (
        <span
          id={popId}
          role="tooltip"
          className="explain-pop"
          style={{ left: 0, top: "calc(100% + 6px)" }}
        >
          <span className="explain-term">{termLabel(term)}</span>
          {copy}
        </span>
      )}
    </span>
  );
}
