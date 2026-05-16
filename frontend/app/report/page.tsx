"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function ReportPage() {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [polished, setPolished] = useState<string | null>(null);
  const [polishing, setPolishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadReport() {
    setMarkdown(null); setPolished(null); setError(null);
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
    setPolished(result?.polished ?? null);
    if (!result) setError("Polish failed — check ANTHROPIC_API_KEY in .env");
    setPolishing(false);
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
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
      </div>

      {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

      {polished && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold mb-3 text-indigo-400">Polished Report</h2>
          <pre className="whitespace-pre-wrap text-sm text-gray-200 bg-gray-900 rounded-lg p-4 leading-relaxed">{polished}</pre>
        </div>
      )}

      {markdown && !polished && (
        <pre className="whitespace-pre-wrap text-sm text-gray-300 bg-gray-900 rounded-lg p-4 leading-relaxed">{markdown}</pre>
      )}

      {!markdown && !error && (
        <p className="text-gray-500 text-sm">Select a date and click Load.</p>
      )}
    </div>
  );
}
