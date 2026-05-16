"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type GameAnalysis } from "@/lib/api";

function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function leanColor(lean: string): string {
  if (lean === "OVER") return "var(--amber)";
  if (lean === "UNDER") return "var(--blue)";
  return "var(--text-3)";
}

function ProbBar({ label, prob, color }: { label: string; prob: number; color: string }) {
  const pct = Math.round(prob * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", width: "36px" }}>{label}</span>
      <div className="stat-bar-track" style={{ flex: 1 }}>
        <div className="stat-bar-fill" style={{ "--fill": `${pct}%`, background: color } as React.CSSProperties} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, fontWeight: 600, width: "32px", textAlign: "right" }}>{pct}%</span>
    </div>
  );
}

function PickCard({ pick, index }: { pick: GameAnalysis; index: number }) {
  const tc = tierColor(pick.ml_tier);
  const isActionable = pick.ml_lean !== "PASS" && pick.ml_tier !== "AVOID";

  return (
    <Link href={`/game/${pick.game_id}`} style={{ textDecoration: "none" }}>
      <div
        className="game-card fade-up"
        style={{
          "--delay": `${index * 40}ms`,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderLeft: `2px solid ${tc}`,
          borderRadius: "6px",
          padding: "16px 20px",
        } as React.CSSProperties}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
            <span style={{ fontWeight: 600, fontSize: "16px", color: "var(--text)", letterSpacing: "-0.02em" }}>
              {pick.away_team_abbr} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>@</span> {pick.home_team_abbr}
            </span>
            {pick.venue && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>{pick.venue}</span>
            )}
          </div>
          <span className="tier-badge" style={{ color: tc, borderColor: tc, opacity: 0.9 }}>
            {pick.ml_tier}
          </span>
        </div>

        {/* Body grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
          {/* Win probability */}
          <div>
            <div style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-3)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.04em" }}>Win Prob</div>
            <ProbBar label={pick.home_team_abbr} prob={pick.model_home_win_prob} color="var(--text)" />
            <ProbBar label={pick.away_team_abbr} prob={pick.model_away_win_prob} color="var(--text-2)" />
          </div>

          {/* Recommendation */}
          <div>
            <div style={{ fontSize: "11px", fontWeight: 500, color: "var(--text-3)", marginBottom: "8px", textTransform: "uppercase", letterSpacing: "0.04em" }}>Signal</div>
            {isActionable ? (
              <div>
                <div style={{ fontWeight: 600, fontSize: "15px", color: tc, letterSpacing: "-0.01em" }}>
                  {pick.ml_lean === "HOME" ? pick.home_team_abbr : pick.away_team_abbr} ML
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "3px" }}>
                  {Math.round(pick.ml_confidence * 100)}% conf · {pick.ml_american_odds > 0 ? "+" : ""}{pick.ml_american_odds}
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--green)", marginTop: "2px" }}>
                  +{((pick.ml_confidence - pick.implied_prob) * 100).toFixed(1)}% edge · {(pick.ml_kelly_fraction * 100).toFixed(1)}% Kelly
                </div>
              </div>
            ) : (
              <div style={{ fontWeight: 500, fontSize: "14px", color: "var(--text-3)" }}>
                {pick.ml_tier === "AVOID" ? "Avoid" : "Pass"}
              </div>
            )}
            {pick.total_lean !== "PASS" && (
              <div style={{ marginTop: "6px", fontFamily: "var(--font-mono)", fontSize: "11px", color: leanColor(pick.total_lean) }}>
                {pick.total_lean} · proj {pick.projected_total.toFixed(1)}
              </div>
            )}
          </div>
        </div>

        {/* Key factors */}
        {pick.key_factors.length > 0 && (
          <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid var(--border)" }}>
            {pick.key_factors.slice(0, 2).map((f, i) => (
              <div key={i} style={{ fontSize: "12px", color: "var(--text-2)", marginBottom: "2px" }}>
                {f}
              </div>
            ))}
          </div>
        )}

        {/* Cautions */}
        {pick.cautions.length > 0 && (
          <div style={{ marginTop: "6px" }}>
            {pick.cautions.slice(0, 2).map((c, i) => (
              <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--amber)", marginBottom: "2px" }}>
                {c}
              </div>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

export default function PicksPage() {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [picks, setPicks] = useState<GameAnalysis[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    api.picks(date).then((p) => {
      if (!alive) return;
      if (p === null) setError(true);
      else setPicks(p);
    });
    return () => { alive = false; };
  }, [date]);

  function changeDate(d: string) {
    setPicks(null); setError(false); setDate(d);
  }

  const actionable = picks?.filter((p) => p.ml_tier === "STRONG LEAN" || p.ml_tier === "LEAN") ?? [];
  const rest = picks?.filter((p) => p.ml_tier !== "STRONG LEAN" && p.ml_tier !== "LEAN") ?? [];

  return (
    <div>
      {/* Page header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px", paddingBottom: "16px", borderBottom: "1px solid var(--border)" }}>
        <div>
          <h1 style={{ fontWeight: 700, fontSize: "20px", letterSpacing: "-0.03em", margin: 0, color: "var(--text)" }}>
            Daily Picks
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "3px" }}>
            Deterministic model · {date}
          </div>
        </div>
        <input
          type="date"
          value={date}
          onChange={(e) => changeDate(e.target.value)}
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 10px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none" }}
        />
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)", padding: "10px 12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px" }}>
          Backend not reachable — run: uvicorn app.api.routes:app --port 8000
        </div>
      )}

      {!error && picks === null && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          Loading…
        </div>
      )}

      {picks?.length === 0 && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          No games found for {date}.
        </div>
      )}

      {actionable.length > 0 && (
        <div style={{ marginBottom: "28px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--green)", marginBottom: "10px", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Actionable — {actionable.length}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {actionable.map((p, i) => <PickCard key={p.game_id} pick={p} index={i} />)}
          </div>
        </div>
      )}

      {rest.length > 0 && (
        <div>
          {actionable.length > 0 && (
            <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-3)", marginBottom: "10px", textTransform: "uppercase", letterSpacing: "0.04em" }}>
              Rest of Slate — {rest.length}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            {rest.map((p, i) => <PickCard key={p.game_id} pick={p} index={actionable.length + i} />)}
          </div>
        </div>
      )}
    </div>
  );
}
