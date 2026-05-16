"use client";

import { useState } from "react";

function impliedProbability(odds: number): number {
  if (odds < 0) return Math.abs(odds) / (Math.abs(odds) + 100);
  return 100 / (odds + 100);
}

function recommendation(edge: number, confidence: number, evidenceQuality: number): string {
  if (confidence < 0.4 || evidenceQuality < 0.4) return "NEED MORE INFO";
  if (edge >= 0.06 && confidence >= 0.7 && evidenceQuality >= 0.7) return "STRONG LEAN";
  if (edge >= 0.03 && confidence >= 0.55) return "LEAN";
  if (edge <= -0.05) return "AVOID";
  return "PASS";
}

const REC_COLOR: Record<string, string> = {
  "STRONG LEAN": "var(--green)",
  "LEAN":        "var(--amber)",
  "AVOID":       "var(--red)",
  "NEED MORE INFO": "var(--orange)",
  "PASS":        "var(--text-2)",
};

function Slider({ label, value, min, max, step, onChange, display }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; display: string;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
        <span style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-2)" }}>{label}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px", color: "var(--amber)", fontWeight: 600 }}>{display}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "var(--amber)", cursor: "pointer" }}
      />
    </div>
  );
}

export default function VerifyPage() {
  const [odds, setOdds] = useState(-110);
  const [modelProb, setModelProb] = useState(0.5);
  const [confidence, setConfidence] = useState(0.6);
  const [evidenceQuality, setEvidenceQuality] = useState(0.6);
  const [result, setResult] = useState<{ impliedProb: number; edge: number; rec: string } | null>(null);

  function evaluate() {
    const impliedProb = impliedProbability(odds);
    const edge = modelProb - impliedProb;
    const rec = recommendation(edge, confidence, evidenceQuality);
    setResult({ impliedProb, edge, rec });
  }

  return (
    <div style={{ maxWidth: "480px" }}>
      <div style={{ borderBottom: "1px solid var(--border)", paddingBottom: "16px", marginBottom: "28px" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "32px", letterSpacing: "0.03em", textTransform: "uppercase", margin: 0 }}>
          Bet Verifier
        </h1>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
          Strong Lean · Lean · Pass · Avoid · Need More Info — not financial advice
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        {/* Odds input */}
        <div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-2)", marginBottom: "8px" }}>
            American Odds
          </div>
          <input
            type="number" value={odds} step={5}
            onChange={e => setOdds(Number(e.target.value))}
            style={{
              width: "100%",
              background: "var(--surface)",
              border: "1px solid var(--border-2)",
              borderRadius: "4px",
              padding: "10px 14px",
              color: "var(--text)",
              fontFamily: "var(--font-mono)",
              fontSize: "18px",
              fontWeight: 600,
            }}
          />
        </div>

        <Slider label="Your estimated probability" value={modelProb} min={0.01} max={0.99} step={0.01} onChange={setModelProb} display={`${(modelProb * 100).toFixed(0)}%`} />
        <Slider label="Confidence in estimate" value={confidence} min={0} max={1} step={0.05} onChange={setConfidence} display={`${(confidence * 100).toFixed(0)}%`} />
        <Slider label="Evidence quality" value={evidenceQuality} min={0} max={1} step={0.05} onChange={setEvidenceQuality} display={`${(evidenceQuality * 100).toFixed(0)}%`} />

        <button
          onClick={evaluate}
          style={{
            background: "var(--amber)",
            color: "var(--bg)",
            border: "none",
            borderRadius: "4px",
            padding: "12px",
            fontFamily: "var(--font-display)",
            fontWeight: 700,
            fontSize: "14px",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            cursor: "pointer",
            transition: "opacity 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = "0.85")}
          onMouseLeave={e => (e.currentTarget.style.opacity = "1")}
        >
          Evaluate
        </button>
      </div>

      {result && (
        <div style={{ marginTop: "24px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "20px", display: "flex", flexDirection: "column", gap: "10px" }}>
          {[
            { label: "Implied Probability", value: `${(result.impliedProb * 100).toFixed(1)}%` },
            { label: "Your Estimate", value: `${(modelProb * 100).toFixed(1)}%` },
            { label: "Edge", value: `${result.edge >= 0 ? "+" : ""}${(result.edge * 100).toFixed(1)}%`, color: result.edge >= 0 ? "var(--green)" : "var(--red)" },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: "10px", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-2)" }}>{label}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px", color: color ?? "var(--text)", fontWeight: 600 }}>{value}</span>
            </div>
          ))}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "4px" }}>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "13px", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-2)" }}>Recommendation</span>
            <span style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "22px", letterSpacing: "0.04em", color: REC_COLOR[result.rec] ?? "var(--text)" }}>
              {result.rec}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
