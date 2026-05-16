"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const METHOD_STYLE: Record<string, { label: string; color: string }> = {
  sdk:  { label: "AI · SDK",  color: "var(--green)" },
  cli:  { label: "AI · CLI",  color: "var(--amber)" },
  none: { label: "Raw",       color: "var(--text-2)" },
};

export default function ReportPage() {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [polishedText, setPolishedText] = useState<string | null>(null);
  const [method, setMethod] = useState<string | null>(null);
  const [polishing, setPolishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadReport() {
    setMarkdown(null); setPolishedText(null); setMethod(null); setError(null);
    try {
      const res = await fetch(`/api/report?date=${date}`);
      if (!res.ok) throw new Error("not found");
      setMarkdown(await res.text());
    } catch {
      setError(`No report for ${date}. Run: python scripts/run_daily_report.py`);
    }
  }

  async function polish() {
    if (!markdown) return;
    setPolishing(true);
    const result = await api.polishReport(markdown);
    if (!result) {
      setError("Polish failed — check ANTHROPIC_API_KEY or Claude CLI install");
    } else {
      setPolishedText(result.markdown);
      setMethod(result.method);
    }
    setPolishing(false);
  }

  const displayText = polishedText ?? markdown;
  const methodMeta = method ? (METHOD_STYLE[method] ?? METHOD_STYLE.none) : null;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "16px", borderBottom: "1px solid var(--border)", paddingBottom: "16px", marginBottom: "24px", flexWrap: "wrap" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "32px", letterSpacing: "0.03em", textTransform: "uppercase", margin: 0 }}>
          Daily Report
        </h1>
        <input
          type="date" value={date}
          onChange={e => setDate(e.target.value)}
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 10px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "12px" }}
        />
        <button
          onClick={loadReport}
          style={{ background: "var(--surface-2)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 14px", color: "var(--text)", fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", cursor: "pointer" }}
        >
          Load
        </button>
        {markdown && (
          <button
            onClick={polish} disabled={polishing}
            style={{ background: polishing ? "var(--border)" : "var(--amber)", border: "none", borderRadius: "4px", padding: "6px 14px", color: polishing ? "var(--text-2)" : "var(--bg)", fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "12px", letterSpacing: "0.06em", textTransform: "uppercase", cursor: polishing ? "not-allowed" : "pointer", transition: "background 0.15s" }}
          >
            {polishing ? "Polishing…" : "Polish with Claude"}
          </button>
        )}
        {methodMeta && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: methodMeta.color, border: `1px solid ${methodMeta.color}`, borderRadius: "3px", padding: "2px 8px", opacity: 0.85 }}>
            {methodMeta.label}
          </span>
        )}
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--orange)", padding: "12px", border: "1px solid var(--orange)", borderRadius: "4px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {displayText ? (
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "12px", lineHeight: 1.7, color: "var(--text)", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "24px" }}>
          {displayText}
        </pre>
      ) : (
        !error && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
            Select a date and click Load.
          </div>
        )
      )}
    </div>
  );
}
