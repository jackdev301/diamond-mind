"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, type SlateGame, type BullpenData, type GameAnalysis } from "@/lib/api";
import { teamLogoUrl } from "@/lib/team-logos";

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
    background: "var(--surface)",
    border: "1px solid var(--border-2)",
    borderRadius: "4px",
    padding: "6px 10px",
    color: "var(--text-2)",
    fontFamily: "var(--font-mono)",
    fontSize: "13px",
    cursor: "pointer",
    lineHeight: 1,
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

function vulnColor(score: number): string {
  if (score >= 70) return "var(--red)";
  if (score >= 50) return "var(--amber)";
  return "var(--green)";
}

function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function VulnBar({ abbr, bp }: { abbr: string; bp: BullpenData }) {
  const color = vulnColor(bp.vulnerability_score);
  const pct = bp.vulnerability_score;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", width: "28px" }}>{abbr}</span>
      <div className="stat-bar-track" style={{ flex: 1 }}>
        <div className="stat-bar-fill" style={{ "--fill": `${pct}%`, "--delay": "80ms", background: color } as React.CSSProperties} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color, fontWeight: 600, width: "28px", textAlign: "right" }}>{pct.toFixed(0)}</span>
    </div>
  );
}

function GameCard({ game, index }: { game: SlateGame; index: number }) {
  const analysis: GameAnalysis | null = game.analysis;
  const hasTier = analysis && analysis.ml_tier !== "PASS" && analysis.ml_lean !== "PASS";
  const tc = hasTier ? tierColor(analysis!.ml_tier) : "var(--border-2)";
  const leanAbbr = analysis?.ml_lean === "HOME" ? game.home_team_abbr
    : analysis?.ml_lean === "AWAY" ? game.away_team_abbr : null;

  return (
    <Link href={`/game/${game.game_id}?date=${game.game_date}`} style={{ textDecoration: "none" }}>
      <div
        className="game-card fade-up infield-divider"
        style={{
          "--delay": `${index * 35}ms`,
          "--clay": hasTier ? tc : "var(--border-2)",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "6px",
          padding: "14px 18px",
          display: "grid",
          gridTemplateColumns: "1fr 130px 1fr",
          gap: "16px",
          alignItems: "center",
        } as React.CSSProperties}
      >
        {/* Matchup */}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <TeamLogo abbr={game.away_team_abbr} size={22} />
            <span style={{ fontWeight: 600, fontSize: "15px", color: "var(--text)", letterSpacing: "-0.02em" }}>{game.away_team_abbr}</span>
            <span style={{ color: "var(--text-3)", fontSize: "13px" }}>@</span>
            <TeamLogo abbr={game.home_team_abbr} size={22} />
            <span style={{ fontWeight: 600, fontSize: "15px", color: "var(--text)", letterSpacing: "-0.02em" }}>{game.home_team_abbr}</span>
          </div>
          {game.venue && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "3px" }}>{game.venue}</div>
          )}
        </div>

        {/* Model signal */}
        <div style={{ textAlign: "center" }}>
          {analysis ? (
            hasTier ? (
              <>
                <div style={{ fontSize: "11px", fontWeight: 600, color: tc, textTransform: "uppercase", letterSpacing: "0.03em" }}>
                  {analysis.ml_tier}
                </div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "var(--text)", marginTop: "2px" }}>
                  {leanAbbr} to win
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-2)", marginTop: "1px" }}>
                  <span className="scoreboard-num" style={{ fontSize: "12px", color: "var(--text)" }}>
                    {Math.round(analysis.ml_confidence * 100)}%
                  </span>{" "}
                  ·{" "}
                  <span className="scoreboard-num" style={{ fontSize: "12px", color: "var(--text)" }}>
                    {(analysis.ml_kelly_fraction * 100).toFixed(1)}%
                  </span>{" "}
                  K
                </div>
              </>
            ) : (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>Pass</div>
            )
          ) : (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>—</div>
          )}
        </div>

        {/* Bullpen */}
        <div>
          <div style={{ fontSize: "10px", fontWeight: 500, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: "6px" }}>Bullpen vuln</div>
          {game.away_bullpen && <VulnBar abbr={game.away_team_abbr} bp={game.away_bullpen} />}
          {game.home_bullpen && <VulnBar abbr={game.home_team_abbr} bp={game.home_bullpen} />}
          {!game.home_bullpen && !game.away_bullpen && <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)" }}>—</div>}
        </div>
      </div>
    </Link>
  );
}

function SlatePageInner() {
  const searchParams = useSearchParams();
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(() => searchParams.get("date") ?? today);
  const [games, setGames] = useState<SlateGame[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    api.slate(date).then((g) => {
      if (!alive) return;
      if (g === null) setError(true);
      else setGames(g);
    });
    return () => { alive = false; };
  }, [date]);

  function changeDate(d: string) { setGames(null); setError(false); setDate(d); }

  return (
    <div style={{ position: "relative" }}>
      <div className="diamond-watermark" aria-hidden="true">
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
          <polygon points="100,16 184,100 100,184 16,100" fill="none" stroke="var(--text)" strokeWidth={1} />
          <polygon points="100,58 142,100 100,142 58,100" fill="none" stroke="var(--text)" strokeWidth={1} />
          <line x1="100" y1="16" x2="100" y2="184" stroke="var(--text)" strokeWidth={1} />
          <line x1="16" y1="100" x2="184" y2="100" stroke="var(--text)" strokeWidth={1} />
        </svg>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px", paddingBottom: "14px", borderBottom: "1px solid var(--border)" }}>
        <div>
          <h1 style={{ fontWeight: 700, fontSize: "20px", letterSpacing: "-0.03em", margin: 0 }}>Daily Slate</h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "3px" }}>{date}</div>
        </div>
        <DateNav date={date} onChange={changeDate} />
      </div>

      {error && <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--red)", padding: "10px 12px", border: "1px solid var(--red)", borderRadius: "4px", marginBottom: "16px" }}>Backend offline — uvicorn app.api.routes:app --port 8000</div>}
      {!error && games === null && <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>Loading…</div>}
      {games?.length === 0 && <div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>No games for {date}.</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {games?.map((g, i) => <GameCard key={g.game_id} game={g} index={i} />)}
      </div>
    </div>
  );
}

export default function SlatePage() {
  return (
    <Suspense fallback={<div style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--text-3)", padding: "40px 0", textAlign: "center" }}>Loading…</div>}>
      <SlatePageInner />
    </Suspense>
  );
}
