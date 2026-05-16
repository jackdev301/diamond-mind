"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type BetRecord, type TrackerSummary, type TrackerSummaryGroup } from "@/lib/api";

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtOdds(o: number): string {
  return o >= 0 ? `+${o}` : `${o}`;
}

function fmtUnits(u: number | null): string {
  if (u === null) return "—";
  const s = u >= 0 ? `+${u.toFixed(2)}u` : `${u.toFixed(2)}u`;
  return s;
}

function resultColor(r: BetRecord["result"]): string {
  if (r === "WIN") return "var(--green)";
  if (r === "LOSS") return "var(--red)";
  if (r === "PUSH") return "var(--text-2)";
  return "var(--amber)";
}

function resultLabel(r: BetRecord["result"]): string {
  if (r === null) return "PENDING";
  return r;
}

function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  return "var(--text-3)";
}

// ── Summary stat block ────────────────────────────────────────────────────────

function SummaryGroup({ label, g }: { label: string; g: TrackerSummaryGroup }) {
  const netColor = g.units_net >= 0 ? "var(--green)" : "var(--red)";
  const winRate = g.wins + g.losses > 0
    ? ((g.wins / (g.wins + g.losses)) * 100).toFixed(0) + "%"
    : "—";
  return (
    <div style={{
      flex: 1, minWidth: 0,
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: "6px",
      padding: "14px 16px",
    }}>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "var(--text-3)",
        marginBottom: "8px",
      }}>{label}</div>
      <div style={{
        fontFamily: "var(--font-display)",
        fontSize: "28px",
        fontWeight: 800,
        letterSpacing: "-0.02em",
        color: netColor,
        lineHeight: 1,
      }}>
        {g.units_net >= 0 ? "+" : ""}{g.units_net.toFixed(2)}u
      </div>
      <div style={{ marginTop: "8px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
        {[
          ["Bets", g.bets],
          ["W", g.wins],
          ["L", g.losses],
          ["P", g.pushes],
          ["Pend", g.pending],
          ["W%", winRate],
          ["Wagered", g.units_wagered.toFixed(1) + "u"],
        ].map(([k, v]) => (
          <div key={k as string} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "9px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em" }}>{k}</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "13px", fontWeight: 600, color: "var(--text)" }}>{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Bet row ───────────────────────────────────────────────────────────────────

function BetRow({
  bet,
  onSettle,
  onDelete,
}: {
  bet: BetRecord;
  onSettle: (id: number, result: "WIN" | "LOSS" | "PUSH") => void;
  onDelete: (id: number) => void;
}) {
  const rc = resultColor(bet.result);
  const tc = tierColor(bet.tier);
  const isPending = bet.result === null;

  const btnBase: React.CSSProperties = {
    fontFamily: "var(--font-mono)",
    fontSize: "10px",
    fontWeight: 700,
    padding: "3px 7px",
    borderRadius: "3px",
    border: "1px solid",
    cursor: "pointer",
    lineHeight: 1,
    letterSpacing: "0.04em",
  };

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "90px 1fr 80px 60px 60px 80px 90px 80px",
      alignItems: "center",
      gap: "10px",
      padding: "8px 12px",
      borderBottom: "1px solid var(--border)",
      background: "var(--surface)",
    }}>
      {/* date */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>
        {bet.game_date}
      </span>

      {/* game + pick */}
      <div style={{ minWidth: 0 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 600 }}>
          {bet.away_team_abbr} @ {bet.home_team_abbr}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "1px" }}>
          {bet.selection}
          {bet.market === "total" && bet.total_line != null && (
            <span style={{ color: "var(--text-3)" }}> · o/u {bet.total_line}</span>
          )}
        </div>
      </div>

      {/* odds */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}>
        {fmtOdds(bet.american_odds)}
      </span>

      {/* units wagered */}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-2)" }}>
        {bet.units}u
      </span>

      {/* tier badge */}
      <span className="tier-badge" style={{ color: tc, borderColor: tc, fontSize: "9px" }}>
        {bet.tier === "STRONG LEAN" ? "SL" : bet.tier === "LEAN" ? "L" : bet.tier}
      </span>

      {/* result badge */}
      <span className="tier-badge" style={{ color: rc, borderColor: rc, fontSize: "9px" }}>
        {resultLabel(bet.result)}
      </span>

      {/* units net */}
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: "12px",
        fontWeight: 700,
        color: bet.units_returned === null
          ? "var(--text-3)"
          : bet.units_returned >= 0 ? "var(--green)" : "var(--red)",
      }}>
        {fmtUnits(bet.units_returned)}
      </span>

      {/* actions */}
      <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
        {isPending && (
          <>
            <button
              onClick={() => onSettle(bet.id, "WIN")}
              style={{ ...btnBase, color: "var(--green)", borderColor: "var(--green)", background: "transparent" }}
              title="Mark WIN"
            >W</button>
            <button
              onClick={() => onSettle(bet.id, "LOSS")}
              style={{ ...btnBase, color: "var(--red)", borderColor: "var(--red)", background: "transparent" }}
              title="Mark LOSS"
            >L</button>
            <button
              onClick={() => onSettle(bet.id, "PUSH")}
              style={{ ...btnBase, color: "var(--text-3)", borderColor: "var(--text-3)", background: "transparent" }}
              title="Mark PUSH"
            >P</button>
          </>
        )}
        <button
          onClick={() => onDelete(bet.id)}
          style={{ ...btnBase, color: "var(--text-3)", borderColor: "var(--border-2)", background: "transparent", marginLeft: isPending ? "2px" : "0" }}
          title="Delete"
        >×</button>
      </div>
    </div>
  );
}

// ── Column headers ────────────────────────────────────────────────────────────

function TableHeader() {
  const cell: React.CSSProperties = {
    fontFamily: "var(--font-mono)",
    fontSize: "9px",
    fontWeight: 700,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: "var(--text-3)",
  };
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "90px 1fr 80px 60px 60px 80px 90px 80px",
      alignItems: "center",
      gap: "10px",
      padding: "6px 12px 6px",
      borderBottom: "1px solid var(--border-2)",
      background: "var(--surface-2)",
    }}>
      <span style={cell}>Date</span>
      <span style={cell}>Game / Pick</span>
      <span style={cell}>Odds</span>
      <span style={cell}>Units</span>
      <span style={cell}>Tier</span>
      <span style={cell}>Result</span>
      <span style={cell}>+/- Units</span>
      <span style={cell}>Actions</span>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

type Tab = "all" | "moneyline" | "total";

function Tabs({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  const tabs: { id: Tab; label: string }[] = [
    { id: "all", label: "All" },
    { id: "moneyline", label: "Moneyline" },
    { id: "total", label: "Over/Under" },
  ];
  return (
    <div style={{ display: "flex", gap: "0", borderBottom: "1px solid var(--border)" }}>
      {tabs.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "11px",
            fontWeight: active === id ? 700 : 500,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            padding: "8px 14px",
            background: "transparent",
            border: "none",
            borderBottom: active === id ? "2px solid var(--blue)" : "2px solid transparent",
            color: active === id ? "var(--text)" : "var(--text-3)",
            cursor: "pointer",
            transition: "color 0.12s",
          }}
        >{label}</button>
      ))}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function TrackerPage() {
  const [bets, setBets] = useState<BetRecord[] | null>(null);
  const [summary, setSummary] = useState<TrackerSummary | null>(null);
  const [tab, setTab] = useState<Tab>("all");
  const [error, setError] = useState(false);
  const [autoTracking, setAutoTracking] = useState(false);
  const [autoResult, setAutoResult] = useState<{ created: number; skipped: number } | null>(null);

  const today = new Date().toISOString().slice(0, 10);

  const load = useCallback(async () => {
    const [b, s] = await Promise.all([
      api.trackerBets(),
      api.trackerSummary(),
    ]);
    if (b === null) { setError(true); return; }
    setBets(b);
    setSummary(s);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleAutoTrack() {
    setAutoTracking(true);
    setAutoResult(null);
    const result = await api.trackerAutoTrack(today);
    setAutoTracking(false);
    if (result) {
      setAutoResult(result);
      await load();
    }
  }

  async function handleSettle(id: number, result: "WIN" | "LOSS" | "PUSH") {
    const updated = await api.trackerSettleBet(id, result);
    if (updated) {
      setBets((prev) => prev?.map((b) => b.id === id ? updated : b) ?? null);
      // refresh summary
      const s = await api.trackerSummary();
      if (s) setSummary(s);
    }
  }

  async function handleDelete(id: number) {
    const ok = await api.trackerDeleteBet(id);
    if (ok) {
      setBets((prev) => prev?.filter((b) => b.id !== id) ?? null);
      const s = await api.trackerSummary();
      if (s) setSummary(s);
    }
  }

  // Filter + sort: pending first, then settled descending by date
  const visible = (bets ?? [])
    .filter((b) => tab === "all" ? true : b.market === (tab === "moneyline" ? "moneyline" : "total"))
    .sort((a, b) => {
      // pending first
      if (a.result === null && b.result !== null) return -1;
      if (a.result !== null && b.result === null) return 1;
      // then by date desc, then id desc
      if (a.game_date !== b.game_date) return a.game_date < b.game_date ? 1 : -1;
      return b.id - a.id;
    });

  const pending = visible.filter((b) => b.result === null);
  const settled = visible.filter((b) => b.result !== null);

  const emptySummary: TrackerSummary = {
    ml: { bets: 0, wins: 0, losses: 0, pushes: 0, pending: 0, units_wagered: 0, units_net: 0 },
    total: { bets: 0, wins: 0, losses: 0, pushes: 0, pending: 0, units_wagered: 0, units_net: 0 },
    combined: { bets: 0, wins: 0, losses: 0, pushes: 0, pending: 0, units_wagered: 0, units_net: 0 },
  };
  const s = summary ?? emptySummary;

  return (
    <div>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
        marginBottom: "20px", paddingBottom: "16px", borderBottom: "1px solid var(--border)",
      }}>
        <div>
          <h1 style={{
            fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "22px",
            letterSpacing: "-0.02em", margin: 0, textTransform: "uppercase",
          }}>Picks Tracker</h1>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)",
            marginTop: "4px",
          }}>
            Performance log · {s.combined.bets} tracked · {s.combined.pending} pending
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
          <button
            onClick={handleAutoTrack}
            disabled={autoTracking}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              padding: "8px 14px",
              borderRadius: "4px",
              border: "1px solid var(--blue)",
              background: autoTracking ? "var(--surface)" : "var(--blue)",
              color: autoTracking ? "var(--blue)" : "#000",
              cursor: autoTracking ? "not-allowed" : "pointer",
              opacity: autoTracking ? 0.7 : 1,
              transition: "opacity 0.12s",
            }}
          >
            {autoTracking ? "Tracking…" : `⚡ Auto-track ${today}`}
          </button>
          {autoResult && (
            <div style={{
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              color: autoResult.created > 0 ? "var(--green)" : "var(--text-3)",
            }}>
              {autoResult.created > 0
                ? `+${autoResult.created} logged · ${autoResult.skipped} already tracked`
                : `All picks already tracked (${autoResult.skipped} skipped)`}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)",
          padding: "10px 12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px",
        }}>
          Backend not reachable — run: uvicorn app.api.routes:app --port 8000
        </div>
      )}

      {/* Summary stats */}
      <div style={{ display: "flex", gap: "10px", marginBottom: "20px", flexWrap: "wrap" }}>
        <SummaryGroup label="Combined" g={s.combined} />
        <SummaryGroup label="Moneyline" g={s.ml} />
        <SummaryGroup label="Over / Under" g={s.total} />
      </div>

      {/* Tabs */}
      <Tabs active={tab} onChange={setTab} />

      {/* Table */}
      {bets === null && !error && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)",
          padding: "40px 0", textAlign: "center",
        }}>Loading…</div>
      )}

      {bets !== null && visible.length === 0 && (
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)",
          padding: "40px 0", textAlign: "center",
        }}>
          No bets tracked yet. Hit ⚡ Auto-track to log today&apos;s picks automatically.
        </div>
      )}

      {visible.length > 0 && (
        <div style={{ border: "1px solid var(--border)", borderRadius: "6px", overflow: "hidden", marginTop: "12px" }}>
          <TableHeader />

          {pending.length > 0 && (
            <>
              <div style={{
                padding: "5px 12px",
                background: "var(--surface-2)",
                fontFamily: "var(--font-mono)",
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--amber)",
                borderBottom: "1px solid var(--border)",
              }}>
                ▸ Pending — {pending.length}
              </div>
              {pending.map((b) => (
                <BetRow key={b.id} bet={b} onSettle={handleSettle} onDelete={handleDelete} />
              ))}
            </>
          )}

          {settled.length > 0 && (
            <>
              <div style={{
                padding: "5px 12px",
                background: "var(--surface-2)",
                fontFamily: "var(--font-mono)",
                fontSize: "9px",
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--text-3)",
                borderBottom: "1px solid var(--border)",
                borderTop: pending.length > 0 ? "1px solid var(--border)" : undefined,
              }}>
                ▸ Settled — {settled.length}
              </div>
              {settled.map((b) => (
                <BetRow key={b.id} bet={b} onSettle={handleSettle} onDelete={handleDelete} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
