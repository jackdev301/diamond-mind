"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const METHOD_STYLE: Record<string, { label: string; color: string }> = {
  sdk:  { label: "AI · SDK",  color: "var(--green)" },
  cli:  { label: "AI · CLI",  color: "var(--amber)" },
  none: { label: "Raw",       color: "var(--text-2)" },
};

function offsetDate(base: string, days: number): string {
  const d = new Date(base + "T12:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
}

function btnStyle(active = true): React.CSSProperties {
  return {
    background: "var(--surface)",
    border: "1px solid var(--border-2)",
    borderRadius: "4px",
    padding: "6px 10px",
    color: active ? "var(--text-2)" : "var(--text-3)",
    fontFamily: "var(--font-mono)",
    fontSize: "13px",
    cursor: "pointer",
    lineHeight: 1,
  };
}

export default function ReportPage() {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [polishedText, setPolishedText] = useState<string | null>(null);
  const [method, setMethod] = useState<string | null>(null);
  const [polishing, setPolishing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function loadReport(d = date) {
    setMarkdown(null); setPolishedText(null); setMethod(null); setError(null); setLoading(true);
    try {
      const res = await fetch(`/api/report?date=${d}`);
      if (!res.ok) throw new Error("not found");
      setMarkdown(await res.text());
    } catch {
      setError(`No report for ${d}. Run: python scripts/run_daily_report.py`);
    } finally {
      setLoading(false);
    }
  }

  function changeDate(d: string) {
    setDate(d);
    loadReport(d);
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

  async function copyText() {
    const text = displayText;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const displayText = polishedText ?? markdown;
  const methodMeta = method ? (METHOD_STYLE[method] ?? METHOD_STYLE.none) : null;

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", borderBottom: "1px solid var(--border)", paddingBottom: "14px", marginBottom: "24px", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{ fontWeight: 700, fontSize: "20px", letterSpacing: "-0.03em", margin: 0, color: "var(--text)" }}>
            Daily Report
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "3px" }}>
            {date}
          </div>
        </div>

        {/* Date nav */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <button style={btnStyle()} onClick={() => changeDate(offsetDate(date, -1))}>←</button>
          <input
            type="date" value={date}
            onChange={e => changeDate(e.target.value)}
            style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 10px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none" }}
          />
          <button style={btnStyle()} onClick={() => changeDate(offsetDate(date, 1))}>→</button>
        </div>

        {/* Load */}
        <button
          onClick={() => loadReport()}
          style={{ background: "var(--surface-2)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 14px", color: "var(--text)", fontFamily: "var(--font-ui)", fontWeight: 600, fontSize: "12px", letterSpacing: "0.03em", cursor: "pointer" }}
        >
          Load
        </button>

        {/* Polish */}
        {markdown && (
          <button
            onClick={polish} disabled={polishing}
            style={{ background: polishing ? "var(--border)" : "var(--amber)", border: "none", borderRadius: "4px", padding: "6px 14px", color: polishing ? "var(--text-2)" : "var(--bg)", fontFamily: "var(--font-ui)", fontWeight: 700, fontSize: "12px", cursor: polishing ? "not-allowed" : "pointer", transition: "background 0.15s" }}
          >
            {polishing ? "Polishing…" : "Polish with Claude"}
          </button>
        )}

        {/* Method badge */}
        {methodMeta && (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: methodMeta.color, border: `1px solid ${methodMeta.color}`, borderRadius: "3px", padding: "2px 8px", opacity: 0.85 }}>
            {methodMeta.label}
          </span>
        )}

        {/* Copy */}
        {displayText && (
          <button
            onClick={copyText}
            style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 12px", color: copied ? "var(--green)" : "var(--text-2)", fontFamily: "var(--font-mono)", fontSize: "11px", cursor: "pointer", transition: "color 0.15s" }}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        )}
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--orange)", padding: "12px", border: "1px solid var(--orange)", borderRadius: "4px", marginBottom: "16px" }}>
          {error}
        </div>
      )}

      {loading && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          Loading…
        </div>
      )}

      {displayText ? (
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font-mono)", fontSize: "12px", lineHeight: 1.7, color: "var(--text)", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "24px" }}>
          {displayText}
        </pre>
      ) : (
        !error && !loading && (
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
            Select a date and click Load — or use ← → to browse.
          </div>
        )
      )}
    </div>
  );
}
