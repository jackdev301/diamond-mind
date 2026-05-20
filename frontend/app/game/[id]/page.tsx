"use client";

import React, { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, type GameContext, type WeatherData, type GameAnalysis, type TeamBatting } from "@/lib/api";
import { teamLogoUrl } from "@/lib/team-logos";
import { Gauge, DuelBar, MethodCompare, GrowthReadout } from "@/components/quant";
import { ExplainTooltip } from "@/components/explain";

function TeamLogo({ abbr, size = 40 }: { abbr: string; size?: number }) {
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

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-3)", marginBottom: "10px" }}>
      {children}
    </div>
  );
}

function StatRow({ label, value, mono = true }: { label: string; value: string | number | null | undefined; mono?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-2)" }}>{label}</span>
      <span style={{ fontFamily: mono ? "var(--font-mono)" : "var(--font-body)", fontSize: "13px", color: "var(--text)", fontWeight: 500 }}>
        {value ?? "—"}
      </span>
    </div>
  );
}

function ScoreBar({ value, color, delay = 0 }: { value: number; color: string; delay?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
      <div className="stat-bar-track" style={{ flex: 1 }}>
        <div
          className="stat-bar-fill"
          style={{ "--fill": `${value}%`, "--delay": `${delay}ms`, background: color } as React.CSSProperties}
        />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color, fontWeight: 600, width: "40px", textAlign: "right" }}>
        {value.toFixed(0)}
      </span>
    </div>
  );
}

function vulnColor(score: number) {
  if (score >= 70) return "var(--red)";
  if (score >= 50) return "var(--orange)";
  return "var(--green)";
}

function BullpenCard({ abbr, bp }: { abbr: string; bp: NonNullable<GameContext["home_bullpen"]> }) {
  const vc = vulnColor(bp.vulnerability_score);
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderTop: `2px solid ${vc}`, borderRadius: "6px", padding: "16px" }}>
      <Label>{abbr} Bullpen</Label>
      <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "14px" }}>
        <div>
          <div style={{ marginBottom: "4px" }}>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", fontWeight: 500 }}>Vulnerability</span>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", marginLeft: "6px" }}>— how exposed the pen is tonight (0 = fresh, 100 = gassed)</span>
          </div>
          <ScoreBar value={bp.vulnerability_score} color={vc} delay={0} />
        </div>
        <div>
          <div style={{ marginBottom: "4px" }}>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", fontWeight: 500 }}>Fatigue</span>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", marginLeft: "6px" }}>— pitcher workload over last 3 days (0 = rested, 100 = maxed out)</span>
          </div>
          <ScoreBar value={bp.fatigue_score} color="var(--text-2)" delay={80} />
        </div>
        <div>
          <div style={{ marginBottom: "4px" }}>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", fontWeight: 500 }}>Available Quality</span>
            <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", marginLeft: "6px" }}>— quality of relievers who can actually pitch tonight (0–100)</span>
          </div>
          <ScoreBar value={bp.available_quality} color="var(--amber)" delay={160} />
        </div>
      </div>

      {(bp.unavailable_relievers?.length ?? 0) > 0 && (
        <div style={{ marginTop: "8px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--red)" }}>
          Can&apos;t pitch tonight: {bp.unavailable_relievers.join(", ")}
        </div>
      )}
      {(bp.limited_relievers?.length ?? 0) > 0 && (
        <div style={{ marginTop: "4px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--orange)" }}>
          Limited (high usage): {bp.limited_relievers.join(", ")}
        </div>
      )}
      {(bp.best_available?.length ?? 0) > 0 && (
        <div style={{ marginTop: "4px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--green)" }}>
          Best available: {bp.best_available.join(", ")}
        </div>
      )}
      <div style={{ marginTop: "12px", fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", fontStyle: "italic", lineHeight: 1.4 }}>
        {bp.betting_implication}
      </div>
    </div>
  );
}

function StarterCard({ abbr, starter }: { abbr: string; starter: NonNullable<GameContext["home_starter"]> | null }) {
  const fipColor = starter?.fip != null
    ? starter.fip <= 3.20 ? "var(--green)" : starter.fip >= 4.50 ? "var(--red)" : "var(--text)"
    : "var(--text)";
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>{abbr} Starting Pitcher</Label>
      {starter ? (
        <>
          <div style={{ fontWeight: 600, fontSize: "15px", marginBottom: "12px", color: "var(--text)", letterSpacing: "-0.01em" }}>
            {starter.pitcher_name}
          </div>
          {starter.insufficient_sample && starter.starts === 0 ? (
            <div style={{ fontSize: "12px", color: "var(--text-2)", lineHeight: 1.45 }}>
              Announced starter. No recent-start sample is available in the database yet, so rate stats are withheld.
            </div>
          ) : (
            <>
              <StatRow label="ERA — Earned Run Average (runs allowed per 9 inn.; lower = better)" value={starter.era?.toFixed(2)} />
              {starter.fip != null && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ fontFamily: "var(--font-body)", fontSize: "13px", color: "var(--text-2)", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                    <ExplainTooltip term="fip">
                      <span>FIP — Fielding-Independent Pitching (K, BB, HR only; luck-neutral; lg avg 3.20)</span>
                    </ExplainTooltip>
                  </span>
                  <span className="scoreboard-num" style={{ fontSize: "14px", color: fipColor }}>
                    {starter.fip.toFixed(2)}
                  </span>
                </div>
              )}
              <StatRow label="WHIP — Walks + Hits per Inning (baserunners allowed; lower = better)" value={starter.whip?.toFixed(2)} />
              <StatRow label="K/9 — Strikeouts per 9 innings (swing-and-miss; higher = better)" value={starter.k_per_9?.toFixed(1)} />
              <StatRow label="BB/9 — Walks per 9 innings (control; lower = better; concern ≥ 4.5)" value={starter.bb_per_9?.toFixed(1)} />
              {starter.babip != null && (
                <StatRow
                  label={`BABIP — Batting Avg on Balls in Play (luck proxy; lg avg .298; ${starter.babip >= 0.340 ? "high = unlucky" : starter.babip <= 0.265 ? "low = lucky" : "normal range"})`}
                  value={starter.babip.toFixed(3)}
                />
              )}
              {starter.avg_pitches_per_start != null && (
                <StatRow label="Avg pitches/start (workload; concern ≥ 105 last outing)" value={starter.avg_pitches_per_start.toFixed(0)} />
              )}
              <StatRow label="Recent trend" value={starter.trend_label?.replace(/_/g, " ")} mono={false} />
            </>
          )}
          {starter.insufficient_sample && (
            <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--amber)" }}>
              Small sample — fewer than 5 starts, use caution
            </div>
          )}
        </>
      ) : (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)" }}>Starter not yet announced</div>
      )}
    </div>
  );
}

function degreesToCompass(deg: number): string {
  const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return dirs[Math.round(deg / 22.5) % 16];
}

function windEffect(speedMph: number, deg: number): string {
  if (speedMph < 6) return "calm — minimal effect on ball flight";
  const dir = deg;
  // "out to CF" range roughly 30°–120° from home plate perspective
  if (dir >= 30 && dir <= 120) return `blowing out to CF — favors hitters, Over lean`;
  if (dir >= 210 && dir <= 300) return `blowing in from CF — suppresses power, Under lean`;
  return `crosswind — limited scoring effect`;
}

function WeatherCard({ w }: { w: WeatherData }) {
  if (w.is_dome) return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>Conditions</Label>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-2)" }}>Indoor venue — weather not a factor.</div>
    </div>
  );
  const tempNote = w.temperature_f != null
    ? w.temperature_f >= 85 ? " (hot — hitter-friendly)" : w.temperature_f <= 50 ? " (cold — pitcher-friendly)" : ""
    : "";
  const windNote = w.wind_speed_mph != null && w.wind_direction_deg != null && w.wind_speed_mph >= 6
    ? windEffect(w.wind_speed_mph, w.wind_direction_deg) : null;
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>Conditions</Label>
      <StatRow
        label={`Temperature${tempNote}`}
        value={w.temperature_f != null ? `${w.temperature_f}°F` : null}
      />
      {w.wind_speed_mph != null && (
        <StatRow
          label={`Wind — ${w.wind_speed_mph} mph from ${w.wind_direction_deg != null ? degreesToCompass(w.wind_direction_deg) : "?"}`}
          value={windNote ?? "calm"}
          mono={false}
        />
      )}
      <StatRow label="Precipitation chance" value={w.precipitation_chance != null ? `${w.precipitation_chance}%` : null} />
    </div>
  );
}

type FormWindow = {
  runs_per_game?: number | null;
  runs_allowed_per_game?: number | null;
  team_ops?: number | null;
  team_woba?: number | null;
  record_wins?: number | null;
  record_losses?: number | null;
  trend_label?: string | null;
  games?: number | null;
};

function CompareRow({ label, home, away, higherBetter = true, fmt = (v: number) => v.toFixed(2) }: {
  label: string;
  home: number | null | undefined;
  away: number | null | undefined;
  higherBetter?: boolean;
  fmt?: (v: number) => string;
}) {
  const hVal = home ?? null;
  const aVal = away ?? null;
  const homeWins = hVal !== null && aVal !== null && (higherBetter ? hVal > aVal : hVal < aVal);
  const awayWins = hVal !== null && aVal !== null && (higherBetter ? aVal > hVal : aVal < hVal);
  const winColor = "var(--text)";
  const loseColor = "var(--text-2)";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", alignItems: "center", padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: homeWins ? winColor : loseColor, fontWeight: homeWins ? 600 : 400, textAlign: "right" }}>
        {hVal !== null ? fmt(hVal) : "—"}
      </span>
      <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", textAlign: "center", letterSpacing: "0.04em" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: awayWins ? winColor : loseColor, fontWeight: awayWins ? 600 : 400, textAlign: "left" }}>
        {aVal !== null ? fmt(aVal) : "—"}
      </span>
    </div>
  );
}

function TeamStatsCard({ homeAbbr, awayAbbr, homeForm, awayForm, homeBatting, awayBatting }: {
  homeAbbr: string;
  awayAbbr: string;
  homeForm: FormWindow | null | undefined;
  awayForm: FormWindow | null | undefined;
  homeBatting?: TeamBatting | null;
  awayBatting?: TeamBatting | null;
}) {
  const hf = homeForm as FormWindow | null;
  const af = awayForm as FormWindow | null;
  if (!hf && !af) return null;
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", marginBottom: "12px" }}>
        <div style={{ fontWeight: 600, fontSize: "14px", color: "var(--text)", textAlign: "right", letterSpacing: "-0.01em" }}>{homeAbbr}</div>
        <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase", textAlign: "center", paddingTop: "3px" }}>L10</div>
        <div style={{ fontWeight: 600, fontSize: "14px", color: "var(--text-2)", textAlign: "left", letterSpacing: "-0.01em" }}>{awayAbbr}</div>
      </div>
      <CompareRow label="R/G — Runs scored per game" home={hf?.runs_per_game} away={af?.runs_per_game} fmt={v => v.toFixed(1)} />
      <CompareRow label="RA/G — Runs allowed per game" home={hf?.runs_allowed_per_game} away={af?.runs_allowed_per_game} higherBetter={false} fmt={v => v.toFixed(1)} />
      <CompareRow label="OPS — On-base + Slugging (overall hitting; lg avg ~.720)" home={hf?.team_ops} away={af?.team_ops} fmt={v => v.toFixed(3)} />
      <CompareRow label="wOBA — Weighted On-Base Avg (quality of contact; lg avg ~.310)" home={hf?.team_woba} away={af?.team_woba} fmt={v => v.toFixed(3)} />
      {(homeBatting?.iso != null || awayBatting?.iso != null) && (
        <CompareRow label="ISO — Isolated Power (SLG−AVG; extra-base hit strength; lg avg ~.162)" home={homeBatting?.iso ?? null} away={awayBatting?.iso ?? null} fmt={v => v.toFixed(3)} />
      )}
      {(homeBatting?.strikeout_rate != null || awayBatting?.strikeout_rate != null) && (
        <CompareRow label="K% — Strikeout rate (lg avg 22.6%; lower = better contact)" home={homeBatting?.strikeout_rate ?? null} away={awayBatting?.strikeout_rate ?? null} higherBetter={false} fmt={v => `${(v * 100).toFixed(1)}%`} />
      )}
      {(homeBatting?.walk_rate != null || awayBatting?.walk_rate != null) && (
        <CompareRow label="BB% — Walk rate (lg avg 8.5%; higher = more patient at plate)" home={homeBatting?.walk_rate ?? null} away={awayBatting?.walk_rate ?? null} fmt={v => `${(v * 100).toFixed(1)}%`} />
      )}
      {(homeBatting?.stolen_base_success_rate != null || awayBatting?.stolen_base_success_rate != null) && (
        <CompareRow label="SB% — Stolen base success rate (break-even 72.7%; elite ≥80%)" home={homeBatting?.stolen_base_success_rate ?? null} away={awayBatting?.stolen_base_success_rate ?? null} fmt={v => `${(v * 100).toFixed(0)}%`} />
      )}
      <CompareRow label="W — Wins (last 10 games)" home={hf?.record_wins} away={af?.record_wins} fmt={v => String(Math.round(v))} />
      <CompareRow label="L — Losses (last 10 games)" home={hf?.record_losses} away={af?.record_losses} higherBetter={false} fmt={v => String(Math.round(v))} />
      {(hf?.trend_label || af?.trend_label) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 1fr", padding: "5px 0", marginTop: "2px" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", textAlign: "right" }}>{hf?.trend_label?.replace(/_/g, " ") ?? "—"}</span>
          <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", textAlign: "center" }}>Trend</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", textAlign: "left" }}>{af?.trend_label?.replace(/_/g, " ") ?? "—"}</span>
        </div>
      )}
    </div>
  );
}

function tierColor(tier: string) {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function AnalysisPanel({ a }: { a: GameAnalysis }) {
  const tc = tierColor(a.ml_tier);
  const isActionable = a.ml_lean !== "PASS" && a.ml_tier !== "AVOID";
  const leanAbbr = a.ml_lean === "HOME" ? a.home_team_abbr : a.away_team_abbr;
  const evPct = a.ev_per_dollar != null ? a.ev_per_dollar * 100 : null;
  const cardClass = a.ml_tier === "STRONG LEAN" ? "card-strong-lean" : a.ml_tier === "LEAN" ? "card-lean" : "";

  return (
    <div style={{ marginBottom: "24px" }}>
      <div className="section-label">Model Verdict</div>

      <div className={cardClass} style={{
        background: "var(--surface)",
        border: `1px solid ${isActionable ? tc : "var(--border)"}`,
        borderRadius: "4px",
        overflow: "hidden",
      }}>
        {/* Verdict header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: "1px solid var(--border)",
          background: isActionable ? `rgba(${a.ml_tier === "STRONG LEAN" ? "63,185,80" : "88,166,255"},0.04)` : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "16px",
        }}>
          <div>
            <div style={{ fontFamily: "var(--font-display)", fontSize: "22px", fontWeight: 800, color: tc, letterSpacing: "0.02em", textTransform: "uppercase", lineHeight: 1 }}>
              {isActionable ? `${leanAbbr} ML` : a.ml_tier}
            </div>
            {isActionable && (
              <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "5px" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text)" }}>
                  {a.ml_american_odds > 0 ? "+" : ""}{a.ml_american_odds}
                </span>
                {" "}· {a.ml_tier}
              </div>
            )}
          </div>

          {isActionable && (
            <div style={{ display: "flex", gap: "24px", textAlign: "right" }}>
              <div>
                <div className="data-label" style={{ textAlign: "right" }}>EV / dollar</div>
                <div style={{
                  fontFamily: "var(--font-mono)",
                  fontWeight: 700,
                  fontSize: "20px",
                  color: evPct != null && evPct > 0 ? "var(--green)" : "var(--red)",
                  lineHeight: 1.1,
                }}>
                  {evPct != null ? `${evPct > 0 ? "+" : ""}${evPct.toFixed(1)}¢` : "—"}
                </div>
                <div style={{ fontSize: "9px", color: "var(--text-3)", marginTop: "2px" }}>per $1 wagered</div>
              </div>
              <div>
                <div className="data-label" style={{ textAlign: "right", display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "4px" }}>
                  Kelly
                  <ExplainTooltip term="uncertainty-kelly" />
                </div>
                <div className="scoreboard-num" style={{ fontSize: "22px", color: "var(--text)", lineHeight: 1.1 }}>
                  {(a.ml_kelly_fraction * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: "9px", color: "var(--text-3)", marginTop: "2px" }}>of bankroll</div>
              </div>
            </div>
          )}
        </div>

        {/* Quant verdict — gauge + duel + growth + method comparison */}
        <div style={{ padding: "18px 20px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 150px", gap: "20px", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginBottom: "10px", display: "flex", alignItems: "center", gap: "4px", flexWrap: "wrap" }}>
                model{" "}
                <span className="scoreboard-num" style={{ fontSize: "13px", color: "var(--text)" }}>
                  {(a.q_p_model * 100).toFixed(1)}%
                </span>{" "}
                →{" "}
                <ExplainTooltip term="bayesian-shrinkage">
                  <span>shrunk</span>
                </ExplainTooltip>{" "}
                <strong className="scoreboard-num" style={{ color: "var(--text)", fontSize: "13px" }}>
                  {(a.q_p_shrunk * 100).toFixed(1)}%
                </strong>{" "}
                vs{" "}
                <ExplainTooltip term="shin-devig">
                  <span>Shin market</span>
                </ExplainTooltip>{" "}
                <span className="scoreboard-num" style={{ fontSize: "13px", color: "var(--text)" }}>
                  {(a.q_shin_vig_free * 100).toFixed(1)}%
                </span>
              </div>
              <DuelBar model={a.q_p_shrunk} market={a.q_shin_vig_free} lower={a.q_ci_low} upper={a.q_ci_high} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "4px" }}>
              <Gauge p={a.q_prob_positive} size={140} />
              <ExplainTooltip term="p-plus-ev">
                <span style={{ fontSize: "9px", color: "var(--text-3)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  P(+EV)
                </span>
              </ExplainTooltip>
            </div>
          </div>
          <div
            className="section-label"
            style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              Bankroll growth
              <ExplainTooltip term="expected-log-growth" />
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
              Doubling
              <ExplainTooltip term="doubling-time" />
            </span>
          </div>
          <GrowthReadout a={a} />
          {isActionable && (
            <div style={{ marginTop: "16px" }}>
              <MethodCompare a={a} />
            </div>
          )}
        </div>

        {/* Win probs + total */}
        <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)", display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0" }}>
          <div style={{ padding: "0 14px 0 0", borderRight: "1px solid var(--border)" }}>
            <div className="data-label" style={{ marginBottom: "8px" }}>Win Probability</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {[
                { abbr: a.home_team_abbr, prob: a.model_home_win_prob, home: true },
                { abbr: a.away_team_abbr, prob: a.model_away_win_prob, home: false },
              ].map(({ abbr, prob }) => (
                <div key={abbr} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "10px", color: "var(--text-3)", width: "30px" }}>{abbr}</span>
                  <div className="stat-bar-track" style={{ flex: 1 }}>
                    <div className="stat-bar-fill" style={{ "--fill": `${prob * 100}%`, background: "var(--blue)" } as React.CSSProperties} />
                  </div>
                  <span className="scoreboard-num" style={{ fontSize: "14px", color: "var(--text)", width: "42px", textAlign: "right" }}>
                    {(prob * 100).toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ padding: "0 14px", borderRight: "1px solid var(--border)" }}>
            <div className="data-label" style={{ marginBottom: "8px" }}>Total (O/U)</div>
            <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "18px", color: a.total_lean === "OVER" ? "var(--amber)" : a.total_lean === "UNDER" ? "var(--blue)" : "var(--text-3)" }}>
              {a.total_lean === "PASS" ? "NO LEAN" : a.total_lean}
            </div>
            <div style={{ fontSize: "10px", color: "var(--text-3)", marginTop: "4px" }}>
              proj <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-2)" }}>{a.projected_total.toFixed(1)}</span> runs
            </div>
          </div>
          <div style={{ padding: "0 0 0 14px" }}>
            <div className="data-label" style={{ marginBottom: "8px", display: "flex", alignItems: "center", gap: "4px" }}>
              Base Rate
              <ExplainTooltip term="vig-overround" />
            </div>
            <div style={{ fontSize: "10px", color: "var(--text-2)", lineHeight: 1.6 }}>
              Home adv: <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>53.5%</span><br/>
              Vig: <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>{a.overround != null ? `${((a.overround - 1) * 100).toFixed(1)}%` : "—"}</span><br/>
              Overround: <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>{a.overround != null ? a.overround.toFixed(4) : "—"}</span>
            </div>
          </div>
        </div>

        {/* Component waterfall */}
        {(() => {
          const homeAbbr = a.home_team_abbr;
          const awayAbbr = a.away_team_abbr;
          const components = [
            { label: "SP / FIP",        val: a.component_fip,       note: "Fielding-independent pitching differential" },
            { label: "Bullpen",         val: a.component_bullpen,   note: "Vulnerability & fatigue gap" },
            { label: "Offense",         val: a.component_offense,   note: "wOBA + R/G vs RA/G" },
            { label: "Form / Splits",   val: a.component_trend,     note: "Trend, H2H, home/road records" },
            { label: "K Matchup",       val: a.component_k_matchup, note: "SP K/9 vs lineup K%" },
            { label: "Weather",         val: a.component_weather,   note: "Wind + temp run scoring effect" },
            { label: "Rest",            val: a.component_rest,      note: "Pitcher days rest + pitch count" },
            { label: "Park",            val: a.component_park,      note: "Ballpark run factor" },
          ].filter(c => Math.abs(c.val) > 0.001);
          if (!components.length) return null;
          const maxAbs = Math.max(...components.map(c => Math.abs(c.val)), 0.01);
          return (
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "10px" }}>
                <div className="data-label">Factor Waterfall</div>
                <div style={{ fontSize: "9px", color: "var(--text-3)", display: "flex", gap: "12px" }}>
                  <span style={{ color: "var(--red)" }}>← {awayAbbr}</span>
                  <span style={{ color: "var(--green)" }}>{homeAbbr} →</span>
                </div>
              </div>
              {components.map(({ label, val, note }) => {
                const pct = (Math.abs(val) / maxAbs) * 80;
                const color = val > 0 ? "var(--green)" : "var(--red)";
                return (
                  <div key={label} style={{ marginBottom: "10px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                      <div>
                        <span style={{ fontSize: "11px", color: "var(--text-2)", fontFamily: "var(--font-mono)" }}>{label}</span>
                        <span style={{ fontSize: "9px", color: "var(--text-3)", marginLeft: "8px" }}>{note}</span>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, fontWeight: 700 }}>
                        {val > 0 ? "+" : ""}{(val * 100).toFixed(2)}%
                      </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "2px" }}>
                      <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
                        {val < 0 && <div style={{ width: `${pct}%`, height: "4px", background: color, borderRadius: "1px" }} />}
                      </div>
                      <div style={{ width: "1px", height: "8px", background: "var(--border-2)", flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        {val > 0 && <div style={{ width: `${pct}%`, height: "4px", background: color, borderRadius: "1px" }} />}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })()}

        {/* Key factors */}
        {a.key_factors.length > 0 && (
          <div style={{ padding: "14px 20px", borderBottom: a.cautions.length > 0 ? "1px solid var(--border)" : "none" }}>
            <div className="data-label" style={{ marginBottom: "8px" }}>Key Factors</div>
            {a.key_factors.map((f, i) => (
              <div key={i} style={{ fontSize: "11px", color: "var(--text-2)", marginBottom: "4px", paddingLeft: "8px", borderLeft: "1px solid var(--border-2)" }}>
                {f}
              </div>
            ))}
          </div>
        )}

        {/* Cautions */}
        {a.cautions.length > 0 && (
          <div style={{ padding: "12px 20px", background: "rgba(240,136,62,0.04)" }}>
            {a.cautions.map((c, i) => (
              <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--orange)", marginBottom: "3px" }}>{c}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MathBlock({ label, formula, explanation }: { label: string; formula: string; explanation: string }) {
  return (
    <div style={{ marginBottom: "16px", paddingBottom: "16px", borderBottom: "1px solid var(--border)" }}>
      <div style={{ fontFamily: "var(--font-body)", fontSize: "12px", fontWeight: 600, color: "var(--text-2)", marginBottom: "4px" }}>{label}</div>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: "12px",
        color: "var(--blue)",
        background: "rgba(59,130,246,0.06)",
        border: "1px solid rgba(59,130,246,0.15)",
        borderRadius: "4px",
        padding: "8px 12px",
        marginBottom: "6px",
        letterSpacing: "0.01em",
        whiteSpace: "pre",
      }}>
        {formula}
      </div>
      <div style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-3)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{explanation}</div>
    </div>
  );
}

function ModelMethodologyPanel({ homeAbbr, awayAbbr, analysis }: {
  homeAbbr: string;
  awayAbbr: string;
  analysis: GameAnalysis | null;
}) {
  const [open, setOpen] = React.useState(false);

  return (
    <div style={{ marginBottom: "24px" }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: "none",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          color: "var(--text-3)",
          fontFamily: "var(--font-mono)",
          fontSize: "11px",
          padding: "6px 12px",
          cursor: "pointer",
          letterSpacing: "0.04em",
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span style={{ fontSize: "10px" }}>{open ? "▲" : "▼"}</span>
        {open ? "HIDE" : "SHOW"} MODEL MATH
      </button>

      {open && (
        <div style={{ marginTop: "12px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "20px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-2)", textTransform: "uppercase", marginBottom: "16px" }}>
            How This Model Works
          </div>

          <MathBlock
            label="Step 1 — Base Win Probability (Home Advantage)"
            formula="P_home = 0.535"
            explanation="Every game starts at 53.5% for the home team. MLB home teams won 53.5% of games from 2022-2024 (down from the old 54% figure — home advantage is slowly declining as travel improves and pitcher usage changes)."
          />

          <MathBlock
            label="Step 2 — Starting Pitcher Quality via FIP"
            formula={`FIP = (13 × HR/9  +  3 × BB/9  −  2 × K/9) / 9  +  3.20\n\nP_home += (away_FIP − home_FIP) × 0.018`}
            explanation="FIP (Fielding-Independent Pitching) strips out luck on balls in play and focuses on what a pitcher truly controls: home runs, walks, and strikeouts. Lower FIP = better pitcher. The constant 3.20 anchors FIP to the same scale as ERA. A 1.0 FIP advantage shifts win probability by 1.8%."
          />

          <MathBlock
            label="Step 3 — Bullpen Vulnerability"
            formula={`Vulnerability = 0.55 × Fatigue  +  0.45 × (100 − AvailableQuality)\n\nP_home += (away_vuln − home_vuln) × 0.0012`}
            explanation="Bullpen vulnerability (0–100) combines how tired the relievers are with how good the available (non-tired) arms are. A 10-point vulnerability edge shifts win probability by 1.2%. If a starter averages under 5.5 IP, the bullpen weight doubles because they'll be used earlier."
          />

          <MathBlock
            label="Step 4 — Offensive Quality"
            formula={`off_adj = [(home_R/G − away_RA/G) − (away_R/G − home_RA/G)] × 0.025\n          + (home_wOBA − away_wOBA) × 0.15\n\nwOBA league avg = .310  (2024 FanGraphs)`}
            explanation={`wOBA (Weighted On-Base Average) weights each way of reaching base by its actual run value:\n  wOBA = (0.69×BB + 0.72×HBP + 0.89×1B + 1.27×2B + 1.62×3B + 2.10×HR) / PA\nEach 0.010 wOBA above average adds 1.5% to win probability.`}
          />

          <MathBlock
            label="Step 5 — Projected Total Runs (for O/U)"
            formula={`proj_home = (home_R/G + away_RA/G) / 2  × SP_suppression\nproj_away = (away_R/G + home_RA/G) / 2  × SP_suppression\n\nSP_suppression = min(1.2, max(0.5, 3.5 / FIP))\nTotal = proj_home + proj_away  × ISO_adj  × park_factor`}
            explanation="We average each team's run scoring vs the opponent's run prevention, then reduce it based on how good the starter is (FIP of 3.50 = neutral 1.0×). ISO (Isolated Power = SLG − AVG, league avg .162) adjusts for extra-base hit power. Park factor scales the total up or down based on historical run environment at this ballpark."
          />

          <MathBlock
            label="Step 6 — Vig Removal (Critical)"
            formula={`raw_home = |home_odds| / (|home_odds| + 100)\nraw_away = |away_odds| / (|away_odds| + 100)\n\noverround  = raw_home + raw_away          // always > 1.0\nvig_free_home = raw_home / overround      // Pinnacle method\nvig_free_away = raw_away / overround\n\nExample: DK −115/−115\n  raw = 0.5349 + 0.5349 = 1.0698  (6.98% vig)\n  vig_free = 0.5349 / 1.0698 = 0.5000`}
            explanation={`Raw implied probabilities from both sides always sum to MORE than 100% — that excess is the bookmaker's margin (vig/juice). A typical DraftKings -115/-115 line has ~7% overround. Comparing model probability to RAW implied understates edge by the full vig — if you see a 52% implied probability on a -110 line, the vig-free number is 50%. We compare model output to the vig-free probability only.`}
          />
          <MathBlock
            label="Step 7 — Edge, EV, and Kelly Bet Sizing"
            formula={`Edge (vig-free) = model_prob − vig_free_implied\n\nEV per dollar = b × p − q\n  where  b = decimal_odds − 1\n         p = model win probability\n         q = 1 − p\n\nKelly fraction = (b × p − q) / b  ×  0.25\n\nExample: model 58%, DK −115\n  b = 100/115 = 0.870\n  EV = 0.870 × 0.58 − 0.42 = +0.0846  (+8.5¢ per $1)\n  Kelly = (0.870×0.58 − 0.42) / 0.870 × 0.25 = 2.4% of bankroll`}
            explanation={`The Kelly Criterion maximizes long-run bankroll growth. We use fractional Kelly (×0.25) — full Kelly is mathematically optimal but has catastrophic drawdowns in practice due to model error. EV per dollar is the clearest signal: +8.5¢ means for every $100 wagered, you expect +$8.50 in long-run profit. Tier thresholds: LEAN = +2.5% vig-free edge, STRONG LEAN = +5% vig-free edge.`}
          />

          {analysis && (
            <div style={{ marginTop: "4px", paddingTop: "14px", borderTop: "1px solid var(--border)" }}>
              <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-3)", marginBottom: "10px", textTransform: "uppercase", letterSpacing: "0.04em" }}>This Game — Numbers</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                {[
                  { label: `${homeAbbr} model prob`, val: `${(analysis.model_home_win_prob * 100).toFixed(1)}%` },
                  { label: `${awayAbbr} model prob`, val: `${(analysis.model_away_win_prob * 100).toFixed(1)}%` },
                  { label: "Vig-free implied", val: `${((analysis.vig_free_implied ?? analysis.implied_prob) * 100).toFixed(1)}%` },
                  { label: "Raw implied (incl vig)", val: `${(analysis.implied_prob * 100).toFixed(1)}%` },
                  { label: "Book vig", val: analysis.overround != null ? `${((analysis.overround - 1) * 100).toFixed(2)}%` : "—" },
                  { label: "Edge (vig-free)", val: analysis.edge_vig_free != null && analysis.ml_lean !== "PASS" ? `${analysis.edge_vig_free >= 0 ? "+" : ""}${(analysis.edge_vig_free * 100).toFixed(2)}%` : "N/A" },
                  { label: "EV per dollar", val: analysis.ev_per_dollar != null && analysis.ml_lean !== "PASS" ? `${analysis.ev_per_dollar >= 0 ? "+" : ""}${(analysis.ev_per_dollar * 100).toFixed(2)}¢` : "N/A" },
                  { label: "Kelly fraction", val: analysis.ml_kelly_fraction > 0 ? `${(analysis.ml_kelly_fraction * 100).toFixed(1)}%` : "0% (no bet)" },
                  { label: "Projected total", val: `${analysis.projected_total.toFixed(1)} runs` },
                ].map(({ label, val }) => (
                  <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-3)" }}>{label}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text)", fontWeight: 600 }}>{val}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const asOf = searchParams.get("date") ?? new Date().toISOString().split("T")[0];
  const [ctx, setCtx] = useState<GameContext | null>(null);
  const [homeBatting, setHomeBatting] = useState<TeamBatting | null>(null);
  const [awayBatting, setAwayBatting] = useState<TeamBatting | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const gameId = Number(id);
    api.context(gameId, asOf).then((c) => {
      setCtx(c);
      setLoading(false);
      if (c) {
        api.batting(c.home_team_id, asOf).then(d => setHomeBatting(d));
        api.batting(c.away_team_id, asOf).then(d => setAwayBatting(d));
      }
    });
  }, [id, searchParams]);

  if (loading) return <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>Loading…</div>;
  if (!ctx) return <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)" }}>Game not found.</div>;

  const analysis = ctx.analysis;

  return (
    <div>
      <Link href={`/?date=${asOf}`} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", textDecoration: "none", letterSpacing: "0.05em" }}>
        ← Slate · {asOf}
      </Link>

      <div style={{ marginTop: "16px", marginBottom: "28px", borderBottom: "1px solid var(--border)", paddingBottom: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <TeamLogo abbr={ctx.away_team_abbr} size={48} />
          <div>
            <h1 style={{ fontWeight: 700, fontSize: "28px", letterSpacing: "-0.03em", margin: 0, lineHeight: 1.1 }}>
              {ctx.away_team_abbr} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>@</span> {ctx.home_team_abbr}
            </h1>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "6px" }}>
              {ctx.venue} · {ctx.game_date}
            </div>
          </div>
          <TeamLogo abbr={ctx.home_team_abbr} size={48} />
        </div>
      </div>

      {/* Team Stats */}
      {(ctx.home_form || ctx.away_form) && (
        <div style={{ marginBottom: "24px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
            Team Stats
          </div>
          <TeamStatsCard
            homeAbbr={ctx.home_team_abbr}
            awayAbbr={ctx.away_team_abbr}
            homeForm={(ctx.home_form as Record<string, unknown>)?.l10 as FormWindow}
            awayForm={(ctx.away_form as Record<string, unknown>)?.l10 as FormWindow}
            homeBatting={homeBatting}
            awayBatting={awayBatting}
          />
        </div>
      )}

      {/* Starters */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
          Starting Pitchers
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <StarterCard abbr={ctx.home_team_abbr} starter={ctx.home_starter} />
          <StarterCard abbr={ctx.away_team_abbr} starter={ctx.away_starter} />
        </div>
      </div>

      {/* Bullpens */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
          Bullpen Intelligence
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          {ctx.home_bullpen && <BullpenCard abbr={ctx.home_team_abbr} bp={ctx.home_bullpen} />}
          {ctx.away_bullpen && <BullpenCard abbr={ctx.away_team_abbr} bp={ctx.away_bullpen} />}
        </div>
      </div>

      {/* Weather */}
      {ctx.weather && (
        <div style={{ maxWidth: "360px", marginBottom: "24px" }}>
          <WeatherCard w={ctx.weather} />
        </div>
      )}

      {/* Analysis */}
      {analysis && <AnalysisPanel a={analysis} />}

      {/* Model methodology */}
      <ModelMethodologyPanel homeAbbr={ctx.home_team_abbr} awayAbbr={ctx.away_team_abbr} analysis={analysis} />
    </div>
  );
}
