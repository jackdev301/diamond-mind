"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type GameAnalysis } from "@/lib/api";

function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--amber)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function leanColor(lean: string): string {
  if (lean === "OVER") return "var(--amber)";
  if (lean === "UNDER") return "var(--green)";
  return "var(--text-3)";
}

function ProbBar({ label, prob, color }: { label: string; prob: number; color: string }) {
  const pct = Math.round(prob * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "11px", letterSpacing: "0.06em", color: "var(--text-2)", width: "40px" }}>{label}</span>
      <div className="stat-bar-track" style={{ flex: 1 }}>
        <div
          className="stat-bar-fill"
          style={{ "--fill": `${pct}%`, background: color } as React.CSSProperties}
        />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color, fontWeight: 600, width: "36px", textAlign: "right" }}>{pct}%</span>
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
          "--delay": `${index * 60}ms`,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderLeft: `3px solid ${tc}`,
          borderRadius: "6px",
          padding: "20px",
        } as React.CSSProperties}
      >
        {/* Header row */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "24px", letterSpacing: "0.02em", lineHeight: 1.1, color: "var(--text)" }}>
              {pick.away_team_abbr} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>@</span> {pick.home_team_abbr}
            </div>
            {pick.venue && (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)", marginTop: "3px" }}>{pick.venue}</div>
            )}
          </div>

          {/* Tier badge */}
          <div style={{
            fontFamily: "var(--font-display)",
            fontWeight: 800,
            fontSize: "11px",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: tc,
            border: `1px solid ${tc}`,
            borderRadius: "3px",
            padding: "4px 10px",
            whiteSpace: "nowrap",
          }}>
            {pick.ml_tier}
          </div>
        </div>

        {/* Body: prob bars + recommendation */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
          {/* Left: win probabilities */}
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "8px" }}>Win Probability</div>
            <ProbBar label={pick.home_team_abbr} prob={pick.model_home_win_prob} color="var(--amber)" />
            <ProbBar label={pick.away_team_abbr} prob={pick.model_away_win_prob} color="var(--text-2)" />
          </div>

          {/* Right: recommendation */}
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "8px" }}>Recommendation</div>
            {isActionable ? (
              <>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "18px", color: tc, letterSpacing: "0.04em" }}>
                  {pick.ml_lean === "HOME" ? pick.home_team_abbr : pick.away_team_abbr} ML
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "2px" }}>
                  {Math.round(pick.ml_confidence * 100)}% conf · Kelly {(pick.ml_kelly_fraction * 100).toFixed(1)}%
                </div>
              </>
            ) : (
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "16px", color: "var(--text-3)" }}>
                {pick.ml_tier === "AVOID" ? "AVOID" : "PASS"}
              </div>
            )}

            {/* Total lean */}
            {pick.total_lean !== "PASS" && (
              <div style={{ marginTop: "8px", fontFamily: "var(--font-mono)", fontSize: "11px", color: leanColor(pick.total_lean) }}>
                Total: {pick.total_lean} · Proj {pick.projected_total.toFixed(1)}
              </div>
            )}
          </div>
        </div>

        {/* Key factors */}
        {pick.key_factors.length > 0 && (
          <div style={{ marginTop: "14px", paddingTop: "12px", borderTop: "1px solid var(--border)" }}>
            {pick.key_factors.slice(0, 3).map((f, i) => (
              <div key={i} style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", marginBottom: "3px" }}>
                · {f}
              </div>
            ))}
          </div>
        )}

        {/* Cautions */}
        {pick.cautions.length > 0 && (
          <div style={{ marginTop: "8px" }}>
            {pick.cautions.map((c, i) => (
              <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--orange)", marginBottom: "2px" }}>
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
    setPicks(null);
    setError(false);
    setDate(d);
  }

  const actionable = picks?.filter((p) => p.ml_tier === "STRONG LEAN" || p.ml_tier === "LEAN") ?? [];
  const rest = picks?.filter((p) => p.ml_tier !== "STRONG LEAN" && p.ml_tier !== "LEAN") ?? [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "28px", borderBottom: "1px solid var(--border)", paddingBottom: "16px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "32px", letterSpacing: "0.03em", textTransform: "uppercase", margin: 0, lineHeight: 1 }}>
            Daily Picks
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
            Algorithmic model · Strong Lean / Lean / Pass / Avoid · {date}
          </div>
        </div>
        <input
          type="date"
          value={date}
          onChange={(e) => changeDate(e.target.value)}
          style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 10px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "12px" }}
        />
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)", padding: "12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px" }}>
          Backend not reachable — run: uvicorn app.api.routes:app --host 0.0.0.0 --port 8000
        </div>
      )}

      {!error && picks === null && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          Running model across slate…
        </div>
      )}

      {picks?.length === 0 && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          No games found for {date}.
        </div>
      )}

      {/* Actionable picks section */}
      {actionable.length > 0 && (
        <div style={{ marginBottom: "32px" }}>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--green)", marginBottom: "12px" }}>
            Actionable ({actionable.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {actionable.map((p, i) => <PickCard key={p.game_id} pick={p} index={i} />)}
          </div>
        </div>
      )}

      {/* Rest of slate */}
      {rest.length > 0 && (
        <div>
          {actionable.length > 0 && (
            <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: "12px" }}>
              Rest of Slate
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            {rest.map((p, i) => <PickCard key={p.game_id} pick={p} index={actionable.length + i} />)}
          </div>
        </div>
      )}
    </div>
  );
}
