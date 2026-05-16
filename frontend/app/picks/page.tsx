"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type GameAnalysis } from "@/lib/api";
import { teamLogoUrl } from "@/lib/team-logos";
import { Gauge, DuelBar, MethodCompare, GrowthReadout, tierColor, pPlusColor } from "@/components/quant";

// ── Track button + unit modal ─────────────────────────────────────────────────

type TrackCtx = {
  game_id: number;
  game_date: string;
  market: "moneyline" | "total";
  selection: string;
  american_odds: number;
  tier: string;
  home_team_abbr: string;
  away_team_abbr: string;
  total_line?: number | null;
  projected_total?: number | null;
};

function TrackModal({
  ctx,
  onClose,
  onTracked,
}: {
  ctx: TrackCtx;
  onClose: () => void;
  onTracked: () => void;
}) {
  const [units, setUnits] = useState("1");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    const u = parseFloat(units);
    if (isNaN(u) || u <= 0) { setErr("Enter a positive number of units."); return; }
    setLoading(true);
    const res = await api.trackerCreateBet({ ...ctx, units: u });
    setLoading(false);
    if (res) { onTracked(); onClose(); }
    else setErr("Failed to track — is the backend running?");
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(8,12,16,0.8)", display: "flex", alignItems: "center", justifyContent: "center",
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "var(--surface)", border: "1px solid var(--border-2)", borderRadius: "8px",
          padding: "20px 24px", width: "300px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "16px", marginBottom: "4px" }}>
          Track Bet
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginBottom: "14px" }}>
          {ctx.away_team_abbr} @ {ctx.home_team_abbr} · {ctx.selection} · {ctx.american_odds >= 0 ? "+" : ""}{ctx.american_odds}
        </div>
        <label style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
          Units
        </label>
        <input
          type="number"
          min="0.1"
          step="0.5"
          value={units}
          onChange={(e) => { setUnits(e.target.value); setErr(""); }}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); if (e.key === "Escape") onClose(); }}
          autoFocus
          style={{
            display: "block", width: "100%", marginTop: "5px", marginBottom: "12px",
            background: "var(--surface-2)", border: "1px solid var(--border-2)",
            borderRadius: "4px", padding: "7px 10px",
            color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: "14px", outline: "none",
          }}
        />
        {err && <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--red)", marginBottom: "10px" }}>{err}</div>}
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={submit}
            disabled={loading}
            style={{
              flex: 1, padding: "8px", borderRadius: "4px",
              background: "var(--green)", border: "none", color: "#000",
              fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.7 : 1,
            }}
          >{loading ? "…" : "Track ✓"}</button>
          <button
            onClick={onClose}
            style={{
              padding: "8px 14px", borderRadius: "4px",
              background: "transparent", border: "1px solid var(--border-2)", color: "var(--text-2)",
              fontFamily: "var(--font-mono)", fontSize: "12px", cursor: "pointer",
            }}
          >Cancel</button>
        </div>
      </div>
    </div>
  );
}

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

function TotalBadge({
  pick,
  trackedKey,
  onTrack,
}: {
  pick: GameAnalysis;
  trackedKey: string;
  onTrack: (ctx: TrackCtx) => void;
}) {
  const isTotalAction = pick.total_tier === "STRONG LEAN" || pick.total_tier === "LEAN";
  if (!isTotalAction) return null;
  const tc = tierColor(pick.total_tier);
  const dir = pick.total_lean; // "OVER" or "UNDER"
  const isTracked = trackedKey !== "";

  function handleTrack(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const sel = dir === "OVER" ? "OVER" : "UNDER";
    // use total odds: total_lean determines which side; we don't have per-side odds in GameAnalysis so use a placeholder
    onTrack({
      game_id: pick.game_id,
      game_date: pick.game_date ?? "",
      market: "total",
      selection: sel,
      american_odds: -110, // standard total line; user can edit in tracker
      tier: pick.total_tier,
      home_team_abbr: pick.home_team_abbr,
      away_team_abbr: pick.away_team_abbr,
      total_line: pick.total_line ?? null,
      projected_total: pick.projected_total ?? null,
    });
  }

  return (
    <div style={{
      marginTop: "10px", padding: "8px 10px",
      border: `1px solid ${tc}22`, borderRadius: "6px",
      background: `${tc}08`,
      display: "flex", alignItems: "center", justifyContent: "space-between",
    }}>
      <div>
        <span style={{ fontFamily: "var(--font-display)", fontSize: "18px", fontWeight: 800, color: tc, textTransform: "uppercase", letterSpacing: "-0.01em" }}>
          {dir}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)", marginLeft: "8px" }}>
          {pick.total_line != null ? `o/u ${pick.total_line}` : ""} · proj {pick.projected_total}
        </span>
        <span className="tier-badge" style={{ color: tc, borderColor: tc, marginLeft: "8px", fontSize: "9px" }}>{pick.total_tier}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-2)" }}>
            P(+) {(pick.qt_prob_positive * 100).toFixed(0)}%
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)" }}>
            Kelly {(pick.qt_kelly_sized * 100).toFixed(1)}%
          </div>
        </div>
        <button
          onClick={handleTrack}
          style={{
            fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700,
            padding: "4px 8px", borderRadius: "3px", border: "1px solid",
            cursor: isTracked ? "default" : "pointer",
            color: isTracked ? "var(--green)" : tc,
            borderColor: isTracked ? "var(--green)" : tc,
            background: "transparent",
            whiteSpace: "nowrap",
          }}
        >
          {isTracked ? "Tracked ✓" : "＋ Track"}
        </button>
      </div>
    </div>
  );
}

function PickCard({
  pick,
  index,
  trackedIds,
  onTrack,
}: {
  pick: GameAnalysis;
  index: number;
  trackedIds: Set<string>;
  onTrack: (ctx: TrackCtx) => void;
}) {
  const tc = tierColor(pick.ml_tier);
  const isMlAction = pick.ml_tier === "STRONG LEAN" || pick.ml_tier === "LEAN";
  const isTotalAction = pick.total_tier === "STRONG LEAN" || pick.total_tier === "LEAN";
  const leanAbbr = pick.ml_lean === "HOME" ? pick.home_team_abbr : pick.ml_lean === "AWAY" ? pick.away_team_abbr : null;
  const slab = isMlAction ? tc : isTotalAction ? tierColor(pick.total_tier) : "var(--border-2)";

  const mlTrackKey = `${pick.game_id}-ml`;
  const totalTrackKey = `${pick.game_id}-total`;
  const mlTracked = trackedIds.has(mlTrackKey);

  function handleMlTrack(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!leanAbbr) return;
    onTrack({
      game_id: pick.game_id,
      game_date: pick.game_date ?? "",
      market: "moneyline",
      selection: leanAbbr,
      american_odds: pick.ml_american_odds,
      tier: pick.ml_tier,
      home_team_abbr: pick.home_team_abbr,
      away_team_abbr: pick.away_team_abbr,
    });
  }

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

          {/* Middle: ML verdict + gauge */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 140px", gap: "20px", alignItems: "center", marginTop: "14px" }}>
            <div>
              {isMlAction && leanAbbr ? (
                <>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <div style={{ fontFamily: "var(--font-display)", fontSize: "30px", fontWeight: 800, color: tc, textTransform: "uppercase", lineHeight: 1, letterSpacing: "-0.02em" }}>
                      {leanAbbr} ML
                    </div>
                    <button
                      onClick={handleMlTrack}
                      style={{
                        fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700,
                        padding: "4px 8px", borderRadius: "3px", border: "1px solid",
                        cursor: mlTracked ? "default" : "pointer",
                        color: mlTracked ? "var(--green)" : tc,
                        borderColor: mlTracked ? "var(--green)" : tc,
                        background: "transparent", whiteSpace: "nowrap",
                        marginTop: "2px",
                      }}
                    >
                      {mlTracked ? "Tracked ✓" : "＋ Track"}
                    </button>
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

          {/* Total pick row */}
          <TotalBadge
            pick={pick}
            trackedKey={trackedIds.has(totalTrackKey) ? totalTrackKey : ""}
            onTrack={(ctx) => onTrack(ctx)}
          />

          {/* Bottom: growth HUD */}
          <div style={{ marginTop: "14px" }}>
            <GrowthReadout a={pick} />
          </div>

          {isMlAction && (
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
  const [trackedIds, setTrackedIds] = useState<Set<string>>(new Set());
  const [trackModal, setTrackModal] = useState<TrackCtx | null>(null);

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

  function handleOpenTrack(ctx: TrackCtx) {
    setTrackModal(ctx);
  }

  function handleTracked() {
    if (!trackModal) return;
    const key = `${trackModal.game_id}-${trackModal.market === "moneyline" ? "ml" : "total"}`;
    setTrackedIds((prev) => new Set([...prev, key]));
    setTrackModal(null);
  }

  const isAction = (p: GameAnalysis) =>
    p.ml_tier === "STRONG LEAN" || p.ml_tier === "LEAN" ||
    p.total_tier === "STRONG LEAN" || p.total_tier === "LEAN";
  const actionable = picks?.filter(isAction) ?? [];
  const rest = picks?.filter((p) => !isAction(p)) ?? [];

  return (
    <div>
      {trackModal && (
        <TrackModal
          ctx={trackModal}
          onClose={() => setTrackModal(null)}
          onTracked={handleTracked}
        />
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "24px", paddingBottom: "16px", borderBottom: "1px solid var(--border)" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "22px", letterSpacing: "-0.02em", margin: 0, textTransform: "uppercase" }}>
            Daily Picks
          </h1>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", marginTop: "4px", display: "flex", alignItems: "center", gap: "7px" }}>
            <span className="live-dot" />
            {picks
              ? `${picks.length} games · ${actionable.length} actionable (ML + O/U) · Shin + Bayesian quant · ${date}`
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
            {actionable.map((p, i) => (
              <PickCard
                key={p.game_id} pick={p} index={i}
                trackedIds={trackedIds} onTrack={handleOpenTrack}
              />
            ))}
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
            {rest.map((p, i) => (
              <PickCard
                key={p.game_id} pick={p} index={actionable.length + i}
                trackedIds={trackedIds} onTrack={handleOpenTrack}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
