"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Game, type BullpenData, type GameAnalysis } from "@/lib/api";

function vulnColor(score: number): string {
  if (score >= 70) return "var(--red)";
  if (score >= 50) return "var(--orange)";
  return "var(--green)";
}

function vulnLabel(score: number): string {
  if (score >= 70) return "HIGH";
  if (score >= 50) return "MOD";
  return "LOW";
}

function ScoreBar({ value, color, delay }: { value: number; color: string; delay: number }) {
  return (
    <div className="stat-bar-track" style={{ flex: 1 }}>
      <div
        className="stat-bar-fill"
        style={{ "--fill": `${value}%`, "--delay": `${delay}ms`, background: color } as React.CSSProperties}
      />
    </div>
  );
}

function BullpenPill({ abbr, bp }: { abbr: string; bp: BullpenData }) {
  const color = vulnColor(bp.vulnerability_score);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "12px", letterSpacing: "0.06em", color: "var(--text-2)", width: "28px" }}>{abbr}</span>
      <ScoreBar value={bp.vulnerability_score} color={color} delay={100} />
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, fontWeight: 600, width: "32px", textAlign: "right" }}>
        {vulnLabel(bp.vulnerability_score)}
      </span>
    </div>
  );
}

function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--amber)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function GameCard({ game, date, index }: { game: Game; date: string; index: number }) {
  const [homeBp, setHomeBp] = useState<BullpenData | null>(null);
  const [awayBp, setAwayBp] = useState<BullpenData | null>(null);
  const [analysis, setAnalysis] = useState<GameAnalysis | null>(null);

  useEffect(() => {
    let alive = true;
    api.bullpen(game.home_team_id, date).then(bp => { if (alive) setHomeBp(bp); });
    api.bullpen(game.away_team_id, date).then(bp => { if (alive) setAwayBp(bp); });
    api.analyze(game.game_id, date).then(a => { if (alive) setAnalysis(a); });
    return () => { alive = false; };
  }, [game, date]);

  const topVuln = Math.max(homeBp?.vulnerability_score ?? 0, awayBp?.vulnerability_score ?? 0);
  const hasAnalysis = analysis && analysis.ml_tier !== "PASS";
  const accentColor = hasAnalysis
    ? tierColor(analysis.ml_tier)
    : topVuln > 0 ? vulnColor(topVuln) : "var(--border-2)";

  const leanAbbr = analysis?.ml_lean === "HOME" ? game.home_team_abbr
    : analysis?.ml_lean === "AWAY" ? game.away_team_abbr : null;

  return (
    <Link href={`/game/${game.game_id}`} style={{ textDecoration: "none" }}>
      <div
        className="game-card fade-up"
        style={{
          "--delay": `${index * 60}ms`,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderLeft: `3px solid ${accentColor}`,
          borderRadius: "6px",
          padding: "16px 20px",
          display: "grid",
          gridTemplateColumns: "1fr auto 1fr",
          gap: "16px",
          alignItems: "center",
        } as React.CSSProperties}
      >
        {/* Left: matchup */}
        <div>
          <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "22px", letterSpacing: "0.02em", lineHeight: 1.1, color: "var(--text)" }}>
            {game.away_team_abbr} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>@</span> {game.home_team_abbr}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
            {game.venue}
          </div>
        </div>

        {/* Center: model pick badge */}
        <div style={{ textAlign: "center", minWidth: "90px" }}>
          {analysis ? (
            analysis.ml_lean !== "PASS" ? (
              <>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "13px", letterSpacing: "0.08em", color: accentColor, textTransform: "uppercase" }}>
                  {analysis.ml_tier}
                </div>
                <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "18px", color: "var(--text)", marginTop: "1px" }}>
                  {leanAbbr} ML
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", marginTop: "1px" }}>
                  {Math.round(analysis.ml_confidence * 100)}% · {(analysis.ml_kelly_fraction * 100).toFixed(1)}% Kelly
                </div>
              </>
            ) : (
              <div style={{ fontFamily: "var(--font-display)", fontWeight: 700, fontSize: "13px", color: "var(--text-3)", letterSpacing: "0.06em" }}>
                PASS
              </div>
            )
          ) : (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)" }}>—</div>
          )}
        </div>

        {/* Right: bullpen bars */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div style={{ fontFamily: "var(--font-display)", fontSize: "10px", fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-3)", textTransform: "uppercase", marginBottom: "2px" }}>
            Bullpen Vuln
          </div>
          {awayBp && game.away_team_abbr && <BullpenPill abbr={game.away_team_abbr} bp={awayBp} />}
          {homeBp && game.home_team_abbr && <BullpenPill abbr={game.home_team_abbr} bp={homeBp} />}
          {!homeBp && !awayBp && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>Loading…</div>
          )}
        </div>
      </div>
    </Link>
  );
}

export default function SlatePage() {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [games, setGames] = useState<Game[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.games(date).then((g) => { if (g === null) setError(true); else setGames(g); });
  }, [date]);

  function changeDate(d: string) {
    setGames(null); setError(false); setDate(d);
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: "28px", borderBottom: "1px solid var(--border)", paddingBottom: "16px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "32px", letterSpacing: "0.03em", textTransform: "uppercase", margin: 0, lineHeight: 1 }}>
            Daily Slate
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginTop: "4px" }}>
            Bullpen intelligence · {date}
          </div>
        </div>
        <input
          type="date"
          value={date}
          onChange={(e) => changeDate(e.target.value)}
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border-2)",
            borderRadius: "4px",
            padding: "6px 10px",
            color: "var(--text)",
            fontFamily: "var(--font-mono)",
            fontSize: "12px",
          }}
        />
      </div>

      {error && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)", padding: "12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px" }}>
          Backend not reachable — run: uvicorn app.api.routes:app --host 0.0.0.0 --port 8000
        </div>
      )}

      {!error && games === null && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          Loading slate…
        </div>
      )}

      {games?.length === 0 && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>
          No games scheduled for {date}.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        {games?.map((g, i) => <GameCard key={g.game_id} game={g} date={date} index={i} />)}
      </div>
    </div>
  );
}
