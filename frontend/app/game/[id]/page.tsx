"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, type GameBundle, type WeatherData, type GameAnalysis } from "@/lib/api";

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

function BullpenCard({ abbr, bp }: { abbr: string; bp: NonNullable<GameBundle["home_bullpen"]> }) {
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

function StarterCard({ abbr, starter }: { abbr: string; starter: NonNullable<GameBundle["home_starter"]> | null }) {
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>{abbr} Starting Pitcher</Label>
      {starter ? (
        <>
          <div style={{ fontWeight: 600, fontSize: "15px", marginBottom: "12px", color: "var(--text)", letterSpacing: "-0.01em" }}>
            {starter.pitcher_name}
          </div>
          <StatRow label="ERA — Earned Run Average (runs allowed per 9 innings; lower = better)" value={starter.era?.toFixed(2)} />
          <StatRow label="WHIP — Walks + Hits per Inning Pitched (baserunners allowed; lower = better)" value={starter.whip?.toFixed(2)} />
          <StatRow label="K/9 — Strikeouts per 9 innings (swing-and-miss ability; higher = better)" value={starter.k_per_9?.toFixed(1)} />
          <StatRow label="Recent trend" value={starter.trend_label?.replace(/_/g, " ")} mono={false} />
          {starter.insufficient_sample && (
            <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--amber)" }}>
              ⚠ Small sample — fewer than 5 starts, use caution
            </div>
          )}
        </>
      ) : (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)" }}>Starter not yet announced</div>
      )}
    </div>
  );
}

function WeatherCard({ w }: { w: WeatherData }) {
  if (w.is_dome) return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>Conditions</Label>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-2)" }}>Indoor venue — weather not a factor.</div>
    </div>
  );
  return (
    <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
      <Label>Conditions</Label>
      <StatRow label="Temperature" value={w.temperature_f != null ? `${w.temperature_f}°F` : null} />
      <StatRow label="Wind" value={w.wind_speed_mph != null ? `${w.wind_speed_mph} mph @ ${w.wind_direction_deg}°` : null} />
      <StatRow label="Precip Chance" value={w.precipitation_chance != null ? `${w.precipitation_chance}%` : null} />
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

function TeamStatsCard({ homeAbbr, awayAbbr, homeForm, awayForm }: {
  homeAbbr: string;
  awayAbbr: string;
  homeForm: FormWindow | null | undefined;
  awayForm: FormWindow | null | undefined;
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

  return (
    <div style={{ marginBottom: "24px" }}>
      <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
        Model Analysis
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderLeft: `3px solid ${tc}`, borderRadius: "6px", padding: "20px" }}>
        {/* Top row */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "16px", marginBottom: "20px" }}>
          {/* Moneyline pick */}
          <div>
            <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "6px" }}>Moneyline Pick</div>
            <div style={{ fontWeight: 700, fontSize: "18px", color: tc, letterSpacing: "-0.02em" }}>
              {isActionable ? `${leanAbbr} to win` : a.ml_tier}
            </div>
            {isActionable && (
              <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px", lineHeight: 1.5 }}>
                <span style={{ fontFamily: "var(--font-mono)" }}>{a.ml_american_odds > 0 ? "+" : ""}{a.ml_american_odds}</span>
                {" "}odds · book implies{" "}
                <span style={{ fontFamily: "var(--font-mono)" }}>{Math.round(a.implied_prob * 100)}%</span>
                {" "}win chance
              </div>
            )}
            {isActionable && (
              <div style={{ fontSize: "11px", color: "var(--green)", marginTop: "4px", lineHeight: 1.5 }}>
                Our model says{" "}
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{Math.round(a.ml_confidence * 100)}%</span>
                {" "}— a{" "}
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>+{((a.ml_confidence - a.implied_prob) * 100).toFixed(1)}%</span>
                {" "}edge over the book
              </div>
            )}
            {isActionable && (
              <div style={{ fontSize: "11px", color: "var(--text-3)", marginTop: "4px" }}>
                Kelly bet size: <span style={{ fontFamily: "var(--font-mono)" }}>{(a.ml_kelly_fraction * 100).toFixed(1)}%</span> of bankroll
              </div>
            )}
          </div>

          {/* Win Probability */}
          <div>
            <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "6px" }}>Model Win Chance</div>
            <div style={{ fontSize: "13px", color: "var(--text)", marginBottom: "4px" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{Math.round(a.model_home_win_prob * 100)}%</span>
              {" "}{a.home_team_abbr} (home)
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-2)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{Math.round(a.model_away_win_prob * 100)}%</span>
              {" "}{a.away_team_abbr} (away)
            </div>
            <div style={{ fontSize: "10px", color: "var(--text-3)", marginTop: "6px", lineHeight: 1.4 }}>
              Based on starting pitching, bullpen, offense, recent form, and park
            </div>
          </div>

          {/* Total runs */}
          <div>
            <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "6px" }}>Combined Runs (O/U)</div>
            <div style={{ fontWeight: 700, fontSize: "18px", letterSpacing: "-0.02em", color: a.total_lean === "OVER" ? "var(--amber)" : a.total_lean === "UNDER" ? "var(--blue)" : "var(--text-3)" }}>
              {a.total_lean === "PASS" ? "No lean" : a.total_lean}
            </div>
            <div style={{ fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
              Model projects <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>{a.projected_total.toFixed(1)}</span> total runs
            </div>
          </div>
        </div>

        {/* Component edges */}
        {(a.sp_advantage || a.bullpen_edge || a.offense_edge) && (
          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "14px" }}>
            {a.sp_advantage && <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "3px", padding: "3px 8px" }}>SP: {a.sp_advantage}</span>}
            {a.bullpen_edge && <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "3px", padding: "3px 8px" }}>BP: {a.bullpen_edge}</span>}
          </div>
        )}

        {/* Component breakdown */}
        {(() => {
          const homeAbbr = a.home_team_abbr;
          const awayAbbr = a.away_team_abbr;
          const components = [
            { label: "Starting Pitcher (FIP)", tooltip: "FIP = Fielding-Independent Pitching — measures strikeouts, walks, HR allowed", val: a.component_fip },
            { label: "Bullpen",                tooltip: "Comparative bullpen vulnerability and fatigue today", val: a.component_bullpen },
            { label: "Offense",                tooltip: "Hitting quality via wOBA — Weighted On-Base Average (lg avg .310)", val: a.component_offense },
            { label: "Recent Form",            tooltip: "Win/loss trend over last 10 games", val: a.component_trend },
            { label: "Strikeout Matchup",      tooltip: "Pitcher K-rate vs opposing lineup's strikeout tendency", val: a.component_k_matchup },
            { label: "Weather",                tooltip: "Wind and temperature effects on run scoring", val: a.component_weather },
            { label: "Pitcher Rest",           tooltip: "<4 days = short rest penalty; 8+ days = possible rust", val: a.component_rest },
            { label: "Park Factor",            tooltip: "How this ballpark boosts or suppresses scoring vs league avg", val: a.component_park },
          ].filter(c => Math.abs(c.val) > 0.001);
          if (components.length === 0) return null;
          const maxAbs = Math.max(...components.map(c => Math.abs(c.val)), 0.01);
          return (
            <div style={{ paddingTop: "14px", borderTop: "1px solid var(--border)", marginBottom: "14px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "10px" }}>
                <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase" }}>Model Breakdown</div>
                <div style={{ display: "flex", gap: "12px", fontSize: "10px", color: "var(--text-3)" }}>
                  <span style={{ color: "var(--red)" }}>← favors {awayAbbr}</span>
                  <span style={{ color: "var(--green)" }}>favors {homeAbbr} →</span>
                </div>
              </div>
              {components.map(({ label, tooltip, val }) => {
                const pct = (Math.abs(val) / maxAbs) * 100;
                const color = val > 0 ? "var(--green)" : "var(--red)";
                return (
                  <div key={label} style={{ marginBottom: "8px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "3px" }}>
                      <span style={{ fontFamily: "var(--font-body)", fontSize: "11px", color: "var(--text-2)" }}>{label}</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, fontWeight: 600 }}>
                        {val > 0 ? "+" : ""}{(val * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div style={{ fontSize: "10px", color: "var(--text-3)", marginBottom: "3px", lineHeight: 1.3 }}>{tooltip}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                      <div style={{ flex: 1, display: "flex", justifyContent: "flex-end" }}>
                        {val < 0 && <div style={{ width: `${pct}%`, height: "5px", background: color, borderRadius: "2px" }} />}
                      </div>
                      <div style={{ width: "2px", height: "10px", background: "var(--border-2)", flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        {val > 0 && <div style={{ width: `${pct}%`, height: "5px", background: color, borderRadius: "2px" }} />}
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
          <div style={{ paddingTop: "14px", borderTop: "1px solid var(--border)" }}>
            <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.04em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "8px" }}>Key Factors</div>
            {a.key_factors.map((f, i) => (
              <div key={i} style={{ fontFamily: "var(--font-body)", fontSize: "12px", color: "var(--text-2)", marginBottom: "4px" }}>· {f}</div>
            ))}
          </div>
        )}

        {/* Cautions */}
        {a.cautions.length > 0 && (
          <div style={{ marginTop: "10px" }}>
            {a.cautions.map((c, i) => (
              <div key={i} style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--orange)", marginBottom: "2px" }}>{c}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [bundle, setBundle] = useState<GameBundle | null>(null);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const gameId = Number(id);
    const today = new Date().toISOString().split("T")[0];
    api.bundle(gameId, today).then((b) => { setBundle(b); setLoading(false); });
    api.weather(gameId).then((w) => setWeather(w));
    api.analyze(gameId, today).then((a) => setAnalysis(a));
  }, [id]);

  if (loading) return <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>Loading…</div>;
  if (!bundle) return <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)" }}>Game not found.</div>;

  return (
    <div>
      <Link href="/" style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", textDecoration: "none", letterSpacing: "0.05em" }}>
        ← Slate
      </Link>

      <div style={{ marginTop: "16px", marginBottom: "28px", borderBottom: "1px solid var(--border)", paddingBottom: "16px" }}>
        <h1 style={{ fontWeight: 700, fontSize: "28px", letterSpacing: "-0.03em", margin: 0, lineHeight: 1.1 }}>
          {bundle.away_team_abbr} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>@</span> {bundle.home_team_abbr}
        </h1>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "6px" }}>
          {bundle.venue} · {bundle.game_date}
        </div>
      </div>

      {/* Team Stats */}
      {(bundle.home_form || bundle.away_form) && (
        <div style={{ marginBottom: "24px" }}>
          <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
            Team Stats
          </div>
          <TeamStatsCard
            homeAbbr={bundle.home_team_abbr}
            awayAbbr={bundle.away_team_abbr}
            homeForm={(bundle.home_form as Record<string, unknown>)?.l10 as FormWindow}
            awayForm={(bundle.away_form as Record<string, unknown>)?.l10 as FormWindow}
          />
        </div>
      )}

      {/* Starters */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
          Starting Pitchers
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          <StarterCard abbr={bundle.home_team_abbr} starter={bundle.home_starter} />
          <StarterCard abbr={bundle.away_team_abbr} starter={bundle.away_starter} />
        </div>
      </div>

      {/* Bullpens */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ fontSize: "11px", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: "var(--text-2)", marginBottom: "12px" }}>
          Bullpen Intelligence
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
          {bundle.home_bullpen && <BullpenCard abbr={bundle.home_team_abbr} bp={bundle.home_bullpen} />}
          {bundle.away_bullpen && <BullpenCard abbr={bundle.away_team_abbr} bp={bundle.away_bullpen} />}
        </div>
      </div>

      {/* Weather */}
      {weather && (
        <div style={{ maxWidth: "360px", marginBottom: "24px" }}>
          <WeatherCard w={weather} />
        </div>
      )}

      {/* Analysis */}
      {analysis && <AnalysisPanel a={analysis} />}
    </div>
  );
}
