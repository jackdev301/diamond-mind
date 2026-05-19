"use client";

import { useEffect } from "react";
import { GLOSSARY, termLabel } from "./explain";

type Props = {
  open: boolean;
  onClose: () => void;
};

/** A single labelled glossary row. */
function Entry({ term, label, copy }: { term: string; label: string; copy: string }) {
  return (
    <div className="glossary-entry" key={term}>
      <div className="ge-term">{label}</div>
      <div className="ge-copy">{copy}</div>
    </div>
  );
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="section-label"
      style={{ marginTop: "22px", marginBottom: "12px", color: "var(--clay)" }}
    >
      {children}
    </div>
  );
}

const QUANT_TERMS = [
  "shin-devig",
  "bayesian-shrinkage",
  "p-plus-ev",
  "uncertainty-kelly",
  "expected-log-growth",
  "doubling-time",
  "vig-overround",
  "brier-score",
  "calibration",
];

const MODEL_TERMS = ["fip", "xfip"];

/**
 * Recommendation tiers. Description copy is verification-only language with no
 * overclaiming or certainty wording. STRONG LEAN / LEAN / PASS / AVOID copy is
 * consistent with the canonical `tiers` glossary entry; NEED MORE INFO is
 * described as a data-sufficiency state.
 */
const TIERS: { name: string; copy: string; color: string }[] = [
  {
    name: "STRONG LEAN",
    copy: "Meaningful edge with high confidence in the estimate. The model's signal clears the strong threshold; still a probabilistic read, not certainty.",
    color: "var(--green)",
  },
  {
    name: "LEAN",
    copy: "Moderate edge. The model favors a side but with less margin or less confidence than a strong lean.",
    color: "var(--blue)",
  },
  {
    name: "PASS",
    copy: "No clear edge. The model's estimate is too close to the vig-free market to express a side.",
    color: "var(--text-3)",
  },
  {
    name: "AVOID",
    copy: "Edge against. The model reads the priced side as worse than the market implies — a flag to stay off, not a side to take.",
    color: "var(--red)",
  },
  {
    name: "NEED MORE INFO",
    copy: "Inputs are incomplete (missing starter, odds, or sample). The model withholds a verdict rather than estimate on thin data.",
    color: "var(--amber)",
  },
];

const MODEL_COMPONENTS = [
  ["FIP differential", "Starter quality gap via fielding-independent pitching (K, BB, HR)."],
  ["Bullpen vulnerability score", "Reliever fatigue blended with available-arm quality (0–100)."],
  ["wOBA-based offense", "Weighted on-base average vs. opponent run prevention."],
  ["Team trend", "Recent form, splits, and head-to-head signal."],
  ["Park factor", "Ballpark run-environment multiplier."],
  ["Weather", "Wind and temperature effect on run scoring (outdoor venues)."],
];

/**
 * Right-side methodology & glossary drawer. Opened by the persistent "?"
 * button in the nav. Closes on scrim click, × button, or Escape.
 */
export function GlossaryPanel({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="glossary-scrim" onClick={onClose} aria-hidden="true" />
      <aside
        className="glossary-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Methodology and glossary"
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            paddingBottom: "14px",
            marginBottom: "4px",
            borderBottom: "1px solid var(--border-2)",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontWeight: 700,
                fontSize: "16px",
                color: "var(--text)",
                letterSpacing: "-0.01em",
              }}
            >
              Methodology &amp; Glossary
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                color: "var(--text-3)",
                marginTop: "3px",
                letterSpacing: "0.04em",
              }}
            >
              How the quant pipeline reads a market
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close glossary"
            style={{
              background: "none",
              border: "1px solid var(--border-2)",
              borderRadius: "4px",
              color: "var(--text-2)",
              fontFamily: "var(--font-mono)",
              fontSize: "14px",
              width: "28px",
              height: "28px",
              cursor: "pointer",
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        <SectionHead>Quant Terms</SectionHead>
        {QUANT_TERMS.map((t) => (
          <Entry key={t} term={t} label={termLabel(t)} copy={GLOSSARY[t]} />
        ))}

        <SectionHead>Recommendation Tiers</SectionHead>
        {TIERS.map((tier) => (
          <div className="glossary-entry" key={tier.name}>
            <div className="ge-term" style={{ color: tier.color }}>
              {tier.name}
            </div>
            <div className="ge-copy">{tier.copy}</div>
          </div>
        ))}

        <SectionHead>Model Components</SectionHead>
        {MODEL_COMPONENTS.map(([name, copy]) => (
          <div className="glossary-entry" key={name}>
            <div className="ge-term">{name}</div>
            <div className="ge-copy">{copy}</div>
          </div>
        ))}
        {MODEL_TERMS.map((t) => (
          <Entry key={t} term={t} label={termLabel(t)} copy={GLOSSARY[t]} />
        ))}
      </aside>
    </>
  );
}
