"use client";

import { useState, useEffect, useRef } from "react";
import { api, todayET, getAdminToken } from "@/lib/api";
import AdminGate from "@/components/AdminGate";

const today = todayET();

export default function AdminPage() {
  const [date, setDate] = useState(today);
  const [unlocked, setUnlocked] = useState(() => Boolean(getAdminToken()));
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [totalLines, setTotalLines] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  // Poll job status while running
  useEffect(() => {
    if (!jobId || status === "done" || status === "error") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const data = await api.adminIngestionStatus(jobId, 200);
        if (!data) return;
        setStatus(data.status);
        setLogs(data.log_tail);
        setTotalLines(data.log_lines_total);
        setError(data.error);
        if (data.status === "done" || data.status === "error") {
          setRunning(false);
          clearInterval(pollRef.current!);
        }
      } catch {
        // ignore transient fetch errors during polling
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobId, status]);

  async function handleRunIngestion() {
    setRunning(true);
    setLogs([]);
    setError(null);
    setStatus("queued");
    setJobId(null);
    try {
      const data = await api.adminRunIngestion(date);
      if (!data) throw new Error("No response from server");
      setJobId(data.job_id);
      setStatus(data.status);
    } catch (e: unknown) {
      setRunning(false);
      setStatus("error");
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const statusColor =
    status === "done"
      ? "text-green-400"
      : status === "error"
        ? "text-red-400"
        : status === "running"
          ? "text-yellow-400"
          : "text-slate-400";

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-start justify-between gap-4 mb-1">
          <h1 className="text-2xl font-bold">Admin</h1>
          <AdminGate onUnlocked={() => setUnlocked(true)} />
        </div>
        <p className="text-slate-400 text-sm mb-6">
          Server-side operations — these run on the Render VM, not your local machine.
        </p>

        {/* Ingestion panel */}
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-5">
          <h2 className="text-lg font-semibold mb-3">Run Pregame Ingestion</h2>
          <p className="text-slate-400 text-sm mb-4">
            Fetches teams, rosters, box scores, and recomputes all form windows for the
            selected date. Runs server-side — no local DB connection needed.
          </p>

          <div className="flex gap-3 items-center mb-4">
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500"
              disabled={running}
            />
            <button
              onClick={handleRunIngestion}
              disabled={running || !unlocked}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
            >
              {running ? "Running…" : "Run Ingestion"}
            </button>
            {status && (
              <span className={`text-sm font-mono ${statusColor}`}>
                {status}
                {jobId && <span className="text-slate-500 ml-2">({jobId})</span>}
              </span>
            )}
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded p-3 text-red-300 text-sm mb-3">
              {error}
            </div>
          )}

          {logs.length > 0 && (
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-slate-500 font-mono">
                  Log output ({totalLines} lines total, showing last {logs.length})
                </span>
              </div>
              <div
                ref={logRef}
                className="bg-slate-950 border border-slate-800 rounded p-3 h-96 overflow-y-auto font-mono text-xs text-slate-300 leading-5"
              >
                {logs.map((line, i) => (
                  <div key={i} className={line.includes("ERROR") || line.includes("WARNING") ? "text-yellow-400" : ""}>
                    {line}
                  </div>
                ))}
                {running && (
                  <div className="text-slate-500 animate-pulse mt-1">▌</div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
