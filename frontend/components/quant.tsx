"use client";

import type { GameAnalysis } from "@/lib/api";

/* ── color helpers ─────────────────────────────────────── */
export function tierColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

export function pPlusColor(p: number): string {
  if (p >= 0.65) return "var(--green)";
  if (p >= 0.55) return "var(--blue)";
  if (p >= 0.45) return "var(--amber)";
  return "var(--red)";
}

const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
const signed = (x: number, d = 2) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d)}%`;

/* ── P(+EV) semicircular gauge ─────────────────────────── */
export function Gauge({ p, size = 132 }: { p: number; size?: number }) {
  const color = pPlusColor(p);
  return (
    <div
      className="gauge"
      style={
        {
          width: size,
          height: size / 2 + 6,
          "--g": Math.round(p * 100),
          "--gauge-color": color,
          clipPath: "inset(0 0 0 0)",
        } as React.CSSProperties
      }
    >
      <div style={{ position: "absolute", bottom: 2, textAlign: "center", width: "100%" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: size / 5.5, color, lineHeight: 1, letterSpacing: "-0.03em" }}>
          {Math.round(p * 100)}
          <span style={{ fontSize: size / 13, color: "var(--text-3)" }}>%</span>
        </div>
        <div style={{ fontSize: 9, letterSpacing: "0.1em", color: "var(--text-3)", textTransform: "uppercase", marginTop: 2 }}>
          P(+EV)
        </div>
      </div>
    </div>
  );
}

/* ── Model-vs-market duel ──────────────────────────────── */
export function DuelBar({ model, market, lower, upper }: { model: number; market: number; lower: number; upper: number }) {
  const lo = Math.min(model, market) - 0.06;
  const hi = Math.max(model, market) + 0.06;
  const span = hi - lo || 1;
  const xOf = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / span) * 100))}%`;
  const ciL = xOf(market + lower);
  const ciW = `${(Math.max(0, ((upper - lower) / span) * 100)).toFixed(1)}%`;
  const edge = model - market;
  const col = edge >= 0 ? "var(--green)" : "var(--red)";
  return (
    <div>
      <div className="duel" style={{ "--w": "100%" } as React.CSSProperties}>
        {/* 95% credible interval band */}
        <div style={{ position: "absolute", top: 0, bottom: 0, left: ciL, width: ciW, background: "rgba(88,166,255,0.15)", borderLeft: "1px dashed rgba(88,166,255,0.4)", borderRight: "1px dashed rgba(88,166,255,0.4)" }} />
        {/* market tick */}
        <div className="duel-tick" style={{ left: xOf(market), background: "var(--text-2)", boxShadow: "0 0 6px var(--text-2)" }} />
        {/* model tick */}
        <div className="duel-tick" style={{ left: xOf(model), background: col, boxShadow: `0 0 7px ${col}` }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 5, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-3)" }}>
        <span>market {pct(market)}</span>
        <span style={{ color: col, fontWeight: 700 }}>edge {signed(edge)}</span>
        <span>model {pct(model)}</span>
      </div>
    </div>
  );
}

/* ── HUD readout chip ──────────────────────────────────── */
export function HudChip({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div className="hud-chip">
      <span className="k">{k}</span>
      <span className="v" style={color ? { color } : undefined}>{v}</span>
    </div>
  );
}

/* ── Sonnet-4.6 vs Opus-4.7 method comparison ──────────── */
export function MethodCompare({ a }: { a: GameAnalysis }) {
  const naiveEdge = a.q_edge_naive;
  const quantEdge = a.q_edge_quant;
  const collapsed = naiveEdge - quantEdge;
  return (
    <div>
      <div className="section-label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
        Devig engine · naive vs quant
        <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
      </div>
      <div className="vs-grid">
        <div className="vs-col naive">
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-2)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
            Sonnet 4.6 theory
          </div>
          <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 10 }}>proportional devig · point estimate · ¼-Kelly</div>
          <Row k="vig-free implied" v={pct(a.q_prop_vig_free)} />
          <Row k="edge (point)" v={signed(naiveEdge)} c={naiveEdge >= 0 ? "var(--green)" : "var(--red)"} />
          <Row k="confidence" v="— none —" c="var(--text-3)" />
          <Row k="Kelly mult" v="0.25 fixed" c="var(--text-3)" />
        </div>
        <div className="vs-spine"><span>VS</span></div>
        <div className="vs-col quant">
          <div style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
            Opus 4.7 quant
          </div>
          <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 10 }}>Shin devig · Bayesian shrink · posterior Kelly</div>
          <Row k={`Shin vig-free (z=${a.q_shin_z.toFixed(3)})`} v={pct(a.q_shin_vig_free)} />
          <Row k="edge (shrunk)" v={signed(quantEdge)} c={quantEdge >= 0 ? "var(--green)" : "var(--red)"} />
          <Row k="P(edge > 0)" v={pct(a.q_prob_positive)} c={pPlusColor(a.q_prob_positive)} />
          <Row k="Kelly mult (derived)" v={a.q_kelly_mult.toFixed(3)} c="var(--blue)" />
        </div>
      </div>
      <div style={{ marginTop: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-2)", paddingLeft: 8, borderLeft: "2px solid var(--amber)" }}>
        Shrinkage collapsed the naive edge by{" "}
        <strong style={{ color: "var(--amber)" }}>{signed(collapsed)}</strong>{" "}
        — the market prior is doing its job. You bet{" "}
        <strong style={{ color: pPlusColor(a.q_prob_positive) }}>{pct(a.q_prob_positive)}</strong>{" "}
        confidence the edge is real, not a point guess.
      </div>
    </div>
  );
}

function Row({ k, v, c }: { k: string; v: string; c?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "4px 0", fontSize: 12 }}>
      <span style={{ fontSize: 10, color: "var(--text-3)", letterSpacing: "0.04em", textTransform: "uppercase" }}>{k}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: c ?? "var(--text)" }}>{v}</span>
    </div>
  );
}

/* ── Growth-rate readout ───────────────────────────────── */
export function GrowthReadout({ a }: { a: GameAnalysis }) {
  const g = a.q_growth_rate;
  const dbl = a.q_doubling_bets;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
      <HudChip k="EV / $1" v={`${a.ev_per_dollar >= 0 ? "+" : ""}${(a.ev_per_dollar * 100).toFixed(1)}¢`} color={a.ev_per_dollar >= 0 ? "var(--green)" : "var(--red)"} />
      <HudChip k="log-growth / bet" v={g > 0 ? `+${(g * 100).toFixed(2)}%` : "0.00%"} color={g > 0 ? "var(--green)" : "var(--text-3)"} />
      <HudChip k="2× bankroll in" v={dbl > 0 ? `${dbl} bets` : "—"} color={dbl > 0 ? "var(--blue)" : "var(--text-3)"} />
      <HudChip k="stake (Kelly)" v={pct(a.q_kelly_sized, 2)} color="var(--purple)" />
    </div>
  );
}
