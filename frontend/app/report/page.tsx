"use client";

import { useState } from "react";
import { api } from "@/lib/api";

const METHOD_LABEL: Record<string, string> = {
  sdk: "AI-Polished (SDK)",
  cli: "AI-Polished (CLI)",
  none: "Raw",
};

const METHOD_COLOR: Record<string, string> = {
  sdk: "bg-indigo-900 text-indigo-300",
  cli: "bg-purple-900 text-purple-300",
  none: "bg-gray-800 text-gray-400",
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
      const text = await res.text();
      setMarkdown(text);
    } catch {
      setError(`No report found for ${date}. Run: python scripts/run_daily_report.py`);
    }
  }

  async function polish() {
    if (!markdown) return;
    setPolishing(true);
    const result = await api.polishReport(markdown);
    if (!result) {
      setError("Polish failed — check that ANTHROPIC_API_KEY is set or Claude Code is installed");
    } else {
      setPolishedText(result.markdown);
      setMethod(result.method);
    }
    setPolishing(false);
  }

  const displayText = polishedText ?? markdown;

  return (
    <div>
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <h1 className="text-2xl font-bold">Daily Report</h1>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded px-3 py-1 text-sm" />
        <button onClick={loadReport}
          className="bg-gray-800 hover:bg-gray-700 px-4 py-1 rounded text-sm transition-colors">
          Load
        </button>
        {markdown && (
          <button onClick={polish} disabled={polishing}
            className="bg-indigo-700 hover:bg-indigo-600 disabled:opacity-50 px-4 py-1 rounded text-sm transition-colors">
            {polishing ? "Polishing..." : "Polish with Claude"}
          </button>
        )}
        {method && (
          <span className={`text-xs px-2 py-1 rounded font-medium ${METHOD_COLOR[method] ?? METHOD_COLOR.none}`}>
            {METHOD_LABEL[method] ?? method}
          </span>
        )}
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      {displayText ? (
        <pre className="whitespace-pre-wrap text-sm text-gray-200 bg-gray-900 rounded-lg p-4 leading-relaxed">{displayText}</pre>
      ) : (
        !error && <p className="text-gray-500 text-sm">Select a date and click Load.</p>
      )}
    </div>
  );
}
