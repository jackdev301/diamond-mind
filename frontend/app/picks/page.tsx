"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type GameAnalysis } from "@/lib/api";
import { teamLogoUrl } from "@/lib/team-logos";
import { Gauge, DuelBar, MethodCompare, GrowthReadout, tierColor, pPlusColor } from "@/components/quant";

function TeamLogo({ abbr, size = 28 }: { abbr: string; size?: number }) {
  return (
    <img
      src={teamLogoUrl(abbr)}
      alt={abbr}
      width={size}
      height={size}
      style={{ objectFit: "contain", flexShrink: 0 }}
      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
    />
  );
}

function offsetDate(base: string, days: number): string {
  const d = new Date(base + "T12:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
}

function DateNav({ date, onChange }: { date: string; onChange: (d: string) => void }) {
  const btnStyle: React.CSSProperties = {
    background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px",
    padding: "6px 10px", color: "var(--text-2)", fontFamily: "var(--font-mono)",
    fontSize: "13px", cursor: "pointer", lineHeight: 1,
  };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
      <button style={btnStyle} onClick={() => onChange(offsetDate(date, -1))}>←</button>
      <input
        type="date" value={date}
        onChange={(e) => onChange(e.target.value)}
        style={{ background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "4px", padding: "6px 10px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "12px", outline: "none" }}
      />
      <button style={btnStyle} onClick={() => onChange(offsetDate(date, 1))}>→</button>
    </div>
  );
}

function PickCard({ pick, index }: { pick: GameAnalysis; index: number }) {
  const tc = tierColor(pick.ml_tier);
  const isActionable = pick.ml_tier === "STRONG LEAN" || pick.ml_tier === "LEAN";
  const leanAbbr = pick.ml_lean === "HOME" ? pick.home_team_abbr : pick.ml_lean === "AWAY" ? pick.away_team_abbr : null;
  const slab = isActionable ? tc : "var(--border-2)";

  return (
    <Link href={`/game/${pick.game_id}?date=${pick.game_date ?? ""}`} style={{ textDecoration: "none" }}>
      <div
        className="fade-up game-card"
        style={{ "--delay": `${index * 45}ms`, "--slab-color": slab } as React.CSSProperties}
      >
        <div className="verdict-slab" style={{ "--slab-color": slab } as React.CSSProperties}>
          {/* Top: matchup + tier */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <TeamLogo abbr={pick.away_team_abbr} size={22} />
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "15px" }}>{pick.away_team_abbr}</span>
              <span style={{ color: "var(--text-3)", fontSize: "12px" }}>@</span>
              <TeamLogo abbr={pick.home_team_abbr} size={22} />
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "15px" }}>{pick.home_team_abbr}</span>
              {pick.venue && <span style={{ fontSize: "10px", color: "var(--text-3)", marginLeft: "4px" }}>{pick.venue}</span>}
            </div>
            <span className="tier-badge" style={{ color: tc, borderColor: tc }}>{pick.ml_tier}</span>
          </div>

          {/* Middle: verdict + gauge */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: "20px", alignItems: "center", marginTop: "14px" }}>
            <div>
              {isActionable && leanAbbr ? (
                <>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: "30px", fontWeight: 800, color: tc, textTransform: "uppercase", lineHeight: 1, letterSpacing: "-0.02em" }}>
                    {leanAbbr} ML
                  </div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-2)", marginTop: "5px" }}>
                    {pick.ml_american_odds > 0 ? "+" : ""}{pick.ml_american_odds} ·{" "}
                    Shin-devigged · shrunk to {(pick.q_p_shrunk * 100).toFixed(1)}%
                  </div>
                </>
              ) : (
                <div style={{ fontFamily: "var(--font-display)", fontSize: "22px", fontWeight: 800, color: "var(--text-3)", textTransform: "uppercase", lineHeight: 1 }}>
                  {pick.ml_tier === "AVOID" ? "AVOID" : "PASS"}
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", fontWeight: 400, marginTop: "5px", textTransform: "none" }}>
                    P(+EV) {(pick.q_prob_positive * 100).toFixed(0)}% — below action threshold
                  </div>
                </div>
              )}
              <div style={{ marginTop: "12px" }}>
                <DuelBar model={pick.q_p_shrunk} market={pick.q_shin_vig_free} lower={pick.q_ci_low} upper={pick.q_ci_high} />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "center" }}>
              <Gauge p={pick.q_prob_positive} size={132} />
            </div>
          </div>

          {/* Bottom: growth HUD */}
          <div style={{ marginTop: "14px" }}>
            <GrowthReadout a={pick} />
          </div>

          {isActionable && (
            <div style={{ marginTop: "14px" }}>
              <MethodCompare a={pick} />
            </div>
          )}

          {/* Factors */}
          {pick.key_factors.length > 0 && (
            <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid var(--border)" }}>
              {pick.key_factors.slice(0, 2).map((f, i) => (
                <div key={i} style={{ fontSize: "10px", color: "var(--text-3)", marginBottom: "2px", paddingLeft: "6px", borderLeft: "1px solid var(--border-2)" }}>{f}</div>
              ))}
              {pick.cautions.slice(0, 1).map((c, i) => (
                <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--orange)", marginTop: "3px" }}>{c}</div>
              ))}
            </div>
          )}
        </div>
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

  function changeDate(d: string) { setPicks(null); setError(false); setDate(d); }

  const actionable = picks?.filter((p) => p.ml_tier === "STRONG LEAN" || p.ml_tier === "LEAN") ?? [];
  const rest = picks?.filter((p) => p.ml_tier !== "STRONG LEAN" && p.ml_tier !== "LEAN") ?? [];

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px", paddingBottom: "16px", borderBottom: "1px solid var(--border)" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "22px", letterSpacing: "-0.02em", margin: 0, textTransform: "uppercase" }}>
            Daily Picks
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "4px", display: "flex", alignItems: "center", gap: "7px" }}>
            <span className="live-dot" />
            {picks
              ? `${picks.length} games · ${actionable.length} actionable · Shin + Bayesian quant · ${date}`
              : `Shin + Bayesian quant model · ${date}`}
          </div>
        </div>
        <DateNav date={date} onChange={changeDate} />
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)", padding: "10px 12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px" }}>
          Backend not reachable — run: uvicorn app.api.routes:app --port 8000
        </div>
      )}
      {!error && picks === null && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>Loading…</div>
      )}
      {picks?.length === 0 && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>No games found for {date}.</div>
      )}

      {actionable.length > 0 && (
        <div style={{ marginBottom: "28px" }}>
          <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--green)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            ▸ Actionable — {actionable.length}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {actionable.map((p, i) => <PickCard key={p.game_id} pick={p} index={i} />)}
          </div>
        </div>
      )}

      {rest.length > 0 && (
        <div>
          {actionable.length > 0 && (
            <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--text-3)", marginBottom: "12px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              ▸ Rest of slate — {rest.length}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {rest.map((p, i) => <PickCard key={p.game_id} pick={p} index={actionable.length + i} />)}
          </div>
        </div>
      )}
    </div>
  );
}
