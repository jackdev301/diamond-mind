"use client";

import { useEffect, useState } from "react";
import { api, type BacktestResult, type CalibrationBucket, type TierHitRate } from "@/lib/api";
import { ExplainTooltip } from "@/components/explain";

/* ── date helpers ──────────────────────────────────────── */
function isoDay(d: Date): string {
  return d.toISOString().split("T")[0];
}
function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDay(d);
}

/* ── shared empty state ────────────────────────────────── */
function Accruing({ label, sub }: { label: string; sub?: string }) {
  return (
    <div className="accruing-state" role="status">
      <span style={{ fontWeight: 700, color: "var(--text-2)", letterSpacing: "0.04em", textTransform: "uppercase", fontSize: "11px" }}>
        {label}
      </span>
      {sub && (
        <span style={{ marginTop: "8px", color: "var(--text-3)", fontSize: "11px", lineHeight: 1.5 }}>
          {sub}
        </span>
      )}
    </div>
  );
}

function ChartFrame({
  title,
  term,
  children,
}: {
  title: string;
  term?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "6px",
        padding: "16px 18px",
      }}
    >
      <div
        className="infield-divider"
        style={{ display: "flex", alignItems: "center", gap: "6px", paddingBottom: "10px", marginBottom: "14px" }}
      >
        <span className="section-label" style={{ margin: 0 }}>
          {title}
        </span>
        {term && <ExplainTooltip term={term} />}
      </div>
      {children}
    </div>
  );
}

/* ── 1 · Calibration ───────────────────────────────────── */
function CalibrationChart({ buckets }: { buckets: CalibrationBucket[] }) {
  const live = buckets.filter((b) => b.n > 0 && b.actual_win_rate != null);
  if (live.length === 0) {
    return (
      <Accruing
        label="Calibration accruing"
        sub="No completed games with a HOME/AWAY lean in this range yet."
      />
    );
  }

  const W = 480;
  const H = 260;
  const pad = { l: 42, r: 16, t: 16, b: 34 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  // X: predicted 50–100%, Y: actual 0–100%
  const xOf = (p: number) => pad.l + ((p - 0.5) / 0.5) * plotW;
  const yOf = (a: number) => pad.t + (1 - a) * plotH;
  const maxN = Math.max(...live.map((b) => b.n), 1);

  return (
    <svg
      className="chart-draw"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Calibration chart: predicted win rate versus observed win rate, with a diagonal perfect-calibration reference line."
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {/* grid */}
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={`y${t}`}>
          <line x1={pad.l} y1={yOf(t)} x2={W - pad.r} y2={yOf(t)} stroke="var(--border)" strokeWidth={1} />
          <text x={pad.l - 8} y={yOf(t) + 3} textAnchor="end" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
            {(t * 100).toFixed(0)}%
          </text>
        </g>
      ))}
      {[0.5, 0.625, 0.75, 0.875, 1].map((p) => (
        <text key={`x${p}`} x={xOf(p)} y={H - 12} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
          {(p * 100).toFixed(0)}%
        </text>
      ))}
      {/* perfect-calibration reference */}
      <line
        x1={xOf(0.5)}
        y1={yOf(0.5)}
        x2={xOf(1)}
        y2={yOf(1)}
        stroke="var(--text-3)"
        strokeWidth={1}
        strokeDasharray="4 4"
      />
      <text x={xOf(0.93)} y={yOf(0.99)} fontSize={8} fontFamily="var(--font-mono)" fill="var(--text-3)">
        perfect
      </text>
      {/* bucket points */}
      {live.map((b) => {
        const r = 4 + Math.sqrt(b.n / maxN) * 9;
        const cx = xOf(b.midpoint);
        const cy = yOf(b.actual_win_rate as number);
        const off = Math.abs((b.actual_win_rate as number) - b.midpoint);
        const col = off <= 0.05 ? "var(--green)" : off <= 0.12 ? "var(--amber)" : "var(--red)";
        return (
          <g key={b.midpoint}>
            <circle cx={cx} cy={cy} r={r} fill={col} fillOpacity={0.22} stroke={col} strokeWidth={1.5} />
            <text x={cx} y={cy - r - 4} textAnchor="middle" fontSize={8} fontFamily="var(--font-mono)" fill="var(--text-2)">
              n={b.n}
            </text>
          </g>
        );
      })}
      {/* axis titles */}
      <text x={pad.l + plotW / 2} y={H - 1} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-2)">
        predicted win rate
      </text>
      <text
        x={12}
        y={pad.t + plotH / 2}
        textAnchor="middle"
        fontSize={9}
        fontFamily="var(--font-mono)"
        fill="var(--text-2)"
        transform={`rotate(-90 12 ${pad.t + plotH / 2})`}
      >
        observed win rate
      </text>
    </svg>
  );
}

/* ── 2 · Tier hit rate ─────────────────────────────────── */
const TIER_ORDER = ["STRONG LEAN", "LEAN", "PASS", "AVOID"];
function tierBarColor(tier: string): string {
  if (tier === "STRONG LEAN") return "var(--green)";
  if (tier === "LEAN") return "var(--blue)";
  if (tier === "AVOID") return "var(--red)";
  return "var(--text-3)";
}

function TierHitRateChart({ rows }: { rows: TierHitRate[] }) {
  const byTier = new Map(rows.map((r) => [r.tier, r]));
  const ordered = TIER_ORDER.map((t) => byTier.get(t) ?? { tier: t, n: 0, hit_rate: null });
  const anyLive = ordered.some((r) => r.n > 0);
  if (!anyLive) {
    return (
      <Accruing
        label="No graded picks yet"
        sub="Tier hit rate populates once completed games carry a tier label."
      />
    );
  }

  const W = 480;
  const rowH = 38;
  const H = ordered.length * rowH + 24;
  const labelW = 110;
  const trackX = labelW + 8;
  const trackW = W - trackX - 56;

  return (
    <svg
      className="chart-draw"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Horizontal bar chart of hit rate per recommendation tier, with sample size per tier."
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {ordered.map((r, i) => {
        const y = 14 + i * rowH;
        const cy = y + rowH / 2 - 7;
        const col = tierBarColor(r.tier);
        const hasData = r.n > 0 && r.hit_rate != null;
        const w = hasData ? (r.hit_rate as number) * trackW : 0;
        return (
          <g key={r.tier}>
            <text x={labelW} y={cy + 3} textAnchor="end" fontSize={10} fontFamily="var(--font-mono)" fontWeight={700} fill={col}>
              {r.tier}
            </text>
            <rect x={trackX} y={cy - 8} width={trackW} height={16} fill="var(--surface-3)" rx={2} />
            {hasData ? (
              <rect x={trackX} y={cy - 8} width={w} height={16} fill={col} fillOpacity={0.85} rx={2} />
            ) : (
              <rect
                x={trackX}
                y={cy - 8}
                width={trackW}
                height={16}
                fill="none"
                stroke="var(--border-2)"
                strokeDasharray="3 3"
                rx={2}
              />
            )}
            {/* 50% reference */}
            <line x1={trackX + trackW * 0.5} y1={cy - 12} x2={trackX + trackW * 0.5} y2={cy + 12} stroke="var(--border-2)" strokeWidth={1} strokeDasharray="2 2" />
            <text x={trackX + trackW + 6} y={cy + 3} fontSize={10} fontFamily="var(--font-mono)" fontWeight={700} fill={hasData ? "var(--text)" : "var(--text-3)"}>
              {hasData ? `${((r.hit_rate as number) * 100).toFixed(0)}%` : "—"}
            </text>
            <text x={trackX + trackW + 6} y={cy + 15} fontSize={8} fontFamily="var(--font-mono)" fill="var(--text-3)">
              [{r.n}]
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── 3 · P&L line (flat vs Kelly) ──────────────────────── */
function linePath(values: number[], xOf: (i: number) => number, yOf: (v: number) => number): string {
  return values.map((v, i) => `${i === 0 ? "M" : "L"} ${xOf(i).toFixed(2)} ${yOf(v).toFixed(2)}`).join(" ");
}

function PLLineChart({ flat, kelly }: { flat: number[]; kelly: number[] }) {
  if (flat.length === 0) {
    return (
      <Accruing
        label="No P&L history"
        sub="P&L simulation needs at least one completed game with a HOME/AWAY lean."
      />
    );
  }

  const W = 480;
  const H = 220;
  const pad = { l: 44, r: 14, t: 16, b: 30 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const all = [...flat, ...kelly, 0];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const n = flat.length;
  const xOf = (i: number) => pad.l + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yOf = (v: number) => pad.t + (1 - (v - min) / span) * plotH;

  const yTicks = 4;
  return (
    <svg
      className="chart-draw"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Cumulative profit and loss in units per game: flat-stake line versus uncertainty-Kelly line, with a zero baseline."
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {Array.from({ length: yTicks + 1 }, (_, i) => {
        const v = min + (span * i) / yTicks;
        const y = yOf(v);
        return (
          <g key={i}>
            <line x1={pad.l} y1={y} x2={W - pad.r} y2={y} stroke="var(--border)" strokeWidth={1} />
            <text x={pad.l - 8} y={y + 3} textAnchor="end" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
              {v >= 0 ? "+" : ""}{v.toFixed(1)}
            </text>
          </g>
        );
      })}
      {/* zero baseline */}
      {min < 0 && max > 0 && (
        <line x1={pad.l} y1={yOf(0)} x2={W - pad.r} y2={yOf(0)} stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 4" />
      )}
      {/* x ticks */}
      {[0, Math.floor((n - 1) / 2), n - 1].filter((v, i, a) => a.indexOf(v) === i).map((i) => (
        <text key={i} x={xOf(i)} y={H - 10} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
          {i + 1}
        </text>
      ))}
      <path d={linePath(flat, xOf, yOf)} fill="none" stroke="var(--blue)" strokeWidth={1.6} />
      <path d={linePath(kelly, xOf, yOf)} fill="none" stroke="var(--green)" strokeWidth={1.6} />
      {n === 1 && (
        <>
          <circle cx={xOf(0)} cy={yOf(flat[0])} r={3} fill="var(--blue)" />
          <circle cx={xOf(0)} cy={yOf(kelly[0])} r={3} fill="var(--green)" />
        </>
      )}
      {/* legend */}
      <g fontFamily="var(--font-mono)" fontSize={9}>
        <rect x={pad.l} y={4} width={10} height={3} fill="var(--blue)" />
        <text x={pad.l + 14} y={9} fill="var(--text-2)">flat</text>
        <rect x={pad.l + 52} y={4} width={10} height={3} fill="var(--green)" />
        <text x={pad.l + 66} y={9} fill="var(--text-2)">Kelly</text>
      </g>
      <text x={pad.l + plotW / 2} y={H - 1} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-2)">
        game #
      </text>
    </svg>
  );
}

/* ── 4 · Kelly bankroll ────────────────────────────────── */
function KellyBankrollChart({ bankroll }: { bankroll: number[] }) {
  if (bankroll.length === 0) {
    return (
      <Accruing
        label="Bankroll curve accruing"
        sub="Starts at 100 units once the first graded game lands."
      />
    );
  }

  const W = 480;
  const H = 220;
  const pad = { l: 46, r: 14, t: 16, b: 30 };
  const plotW = W - pad.l - pad.r;
  const plotH = H - pad.t - pad.b;
  const series = [100, ...bankroll];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const span = max - min || 1;
  const n = series.length;
  const xOf = (i: number) => pad.l + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const yOf = (v: number) => pad.t + (1 - (v - min) / span) * plotH;
  const line = linePath(series, xOf, yOf);
  const area = `${line} L ${xOf(n - 1).toFixed(2)} ${yOf(min).toFixed(2)} L ${xOf(0).toFixed(2)} ${yOf(min).toFixed(2)} Z`;
  const last = bankroll[bankroll.length - 1];
  const lastCol = last >= 100 ? "var(--green)" : "var(--red)";

  return (
    <svg
      className="chart-draw"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label="Uncertainty-Kelly bankroll value over time, starting from 100 units, with a 100-unit reference line."
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {[0, 0.25, 0.5, 0.75, 1].map((t) => {
        const v = min + span * t;
        const y = yOf(v);
        return (
          <g key={t}>
            <line x1={pad.l} y1={y} x2={W - pad.r} y2={y} stroke="var(--border)" strokeWidth={1} />
            <text x={pad.l - 8} y={y + 3} textAnchor="end" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
              {v.toFixed(0)}
            </text>
          </g>
        );
      })}
      {min < 100 && max > 100 && (
        <line x1={pad.l} y1={yOf(100)} x2={W - pad.r} y2={yOf(100)} stroke="var(--text-3)" strokeWidth={1} strokeDasharray="4 4" />
      )}
      <path d={area} fill="rgba(63,185,80,0.07)" stroke="none" />
      <path d={line} fill="none" stroke="var(--green)" strokeWidth={1.8} />
      <circle cx={xOf(n - 1)} cy={yOf(series[n - 1])} r={3} fill={lastCol} />
      <text x={xOf(n - 1) - 4} y={yOf(series[n - 1]) - 8} textAnchor="end" fontSize={10} fontFamily="var(--font-mono)" fontWeight={700} fill={lastCol}>
        {last.toFixed(1)}
      </text>
      {[0, n - 1].map((i) => (
        <text key={i} x={xOf(i)} y={H - 10} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-3)">
          {i}
        </text>
      ))}
      <text x={pad.l + plotW / 2} y={H - 1} textAnchor="middle" fontSize={9} fontFamily="var(--font-mono)" fill="var(--text-2)">
        bets placed
      </text>
    </svg>
  );
}

/* ── 5 · Brier readout ─────────────────────────────────── */
function BrierReadout({ brier }: { brier: number | null }) {
  if (brier === null) {
    return (
      <Accruing
        label="Brier score accruing"
        sub="Needs at least one completed game to score the forecast."
      />
    );
  }
  const baseline = 0.25;
  const col = brier < baseline ? "var(--green)" : brier > baseline ? "var(--red)" : "var(--amber)";
  // visual scale: 0 (best) → 0.5 (worst); clamp
  const scale = (v: number) => `${Math.max(0, Math.min(100, (v / 0.5) * 100))}%`;

  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-end", gap: "12px", marginBottom: "16px" }}>
        <span className="scoreboard-num" style={{ fontSize: "44px", color: col, lineHeight: 0.9 }}>
          {brier.toFixed(4)}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", paddingBottom: "6px" }}>
          {brier < baseline ? "better than a coin flip" : brier > baseline ? "worse than a coin flip" : "coin-flip equivalent"}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)", width: "92px", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Model
          </span>
          <div className="stat-bar-track" style={{ flex: 1, height: "6px" }}>
            <div className="stat-bar-fill" style={{ "--fill": scale(brier), background: col } as React.CSSProperties} />
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: col, fontWeight: 700, width: "52px", textAlign: "right" }}>
            {brier.toFixed(4)}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--text-3)", width: "92px", textTransform: "uppercase", letterSpacing: "0.04em" }}>
            Coin flip
          </span>
          <div className="stat-bar-track" style={{ flex: 1, height: "6px" }}>
            <div className="stat-bar-fill" style={{ "--fill": scale(baseline), background: "var(--text-3)" } as React.CSSProperties} />
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--text-3)", fontWeight: 700, width: "52px", textAlign: "right" }}>
            0.2500
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── summary strip ─────────────────────────────────────── */
function SummaryStat({
  label,
  value,
  color,
  term,
}: {
  label: string;
  value: string;
  color?: string;
  term?: string;
}) {
  return (
    <div className="bsg-cell" style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <span
        style={{
          fontSize: "9px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--text-3)",
          display: "flex",
          alignItems: "center",
          gap: "4px",
        }}
      >
        {label}
        {term && <ExplainTooltip term={term} />}
      </span>
      <span className="scoreboard-num" style={{ fontSize: "22px", color: color ?? "var(--text)" }}>
        {value}
      </span>
    </div>
  );
}

/* ── date input ────────────────────────────────────────── */
function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
      <span style={{ fontSize: "9px", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-3)" }}>
        {label}
      </span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border-2)",
          borderRadius: "4px",
          padding: "6px 10px",
          color: "var(--text)",
          fontFamily: "var(--font-mono)",
          fontSize: "12px",
          outline: "none",
        }}
      />
    </label>
  );
}

function ChartSkeleton() {
  return (
    <div
      style={{
        height: "200px",
        borderRadius: "6px",
        background: "linear-gradient(90deg, var(--surface) 0%, var(--surface-2) 50%, var(--surface) 100%)",
        backgroundSize: "200% 100%",
        animation: "fillBar 1.1s linear infinite alternate",
        border: "1px solid var(--border)",
      }}
    />
  );
}

export default function TrackRecordPage() {
  const [start, setStart] = useState(() => daysAgo(90));
  const [end, setEnd] = useState(() => daysAgo(0));
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let alive = true;
    setState("loading");
    setResult(null);
    api.backtest(start, end).then((r) => {
      if (!alive) return;
      if (r === null) {
        setState("error");
      } else {
        setResult(r);
        setState("ready");
      }
    });
    return () => {
      alive = false;
    };
  }, [start, end]);

  const flatTotal = result?.flat_pnl_total ?? 0;
  const kellyTotal = result?.kelly_pnl_total ?? 0;

  return (
    <div style={{ position: "relative" }}>
      {/* decorative infield diamond watermark */}
      <div className="diamond-watermark" aria-hidden="true">
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg">
          <polygon points="100,16 184,100 100,184 16,100" fill="none" stroke="var(--text)" strokeWidth={1} />
          <polygon points="100,58 142,100 100,142 58,100" fill="none" stroke="var(--text)" strokeWidth={1} />
          <line x1="100" y1="16" x2="100" y2="184" stroke="var(--text)" strokeWidth={1} />
          <line x1="16" y1="100" x2="184" y2="100" stroke="var(--text)" strokeWidth={1} />
        </svg>
      </div>

      {/* header */}
      <div
        className="infield-divider"
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "22px",
          paddingBottom: "16px",
        }}
      >
        <div>
          <h1
            className="scoreboard-num"
            style={{ fontSize: "30px", margin: 0, color: "var(--text)", textTransform: "uppercase", lineHeight: 1 }}
          >
            Track Record
          </h1>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "11px",
              color: "var(--text-3)",
              marginTop: "6px",
              letterSpacing: "0.03em",
            }}
          >
            Deterministic model replay over completed games · real box-score outcomes, no stored picks
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: "10px" }}>
          <DateField label="From" value={start} onChange={setStart} />
          <DateField label="To" value={end} onChange={setEnd} />
        </div>
      </div>

      {state === "error" && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "12px",
            color: "var(--red)",
            padding: "10px 12px",
            border: "1px solid var(--red)",
            borderRadius: "4px",
            marginBottom: "16px",
          }}
        >
          Backtest endpoint not reachable — run: uvicorn app.api.routes:app --port 8000
        </div>
      )}

      {state === "loading" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <ChartSkeleton />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <ChartSkeleton />
            <ChartSkeleton />
          </div>
        </div>
      )}

      {state === "ready" && result && result.n === 0 && (
        <div className="accruing-state" style={{ padding: "56px 24px" }} role="status">
          <span style={{ fontWeight: 700, color: "var(--text-2)", fontSize: "13px", letterSpacing: "0.04em", textTransform: "uppercase" }}>
            No completed games in range
          </span>
          <span style={{ marginTop: "10px", color: "var(--text-3)", fontSize: "12px", lineHeight: 1.6, maxWidth: "440px", margin: "10px auto 0" }}>
            The backtest found zero finished games with box-score results between{" "}
            <strong style={{ color: "var(--text-2)" }}>{result.start_date}</strong> and{" "}
            <strong style={{ color: "var(--text-2)" }}>{result.end_date}</strong>. Widen the date
            range or pick a window with played games. Nothing is fabricated to fill this view.
          </span>
        </div>
      )}

      {state === "ready" && result && result.n > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* summary strip — box-score grid */}
          <div
            className="box-score-grid"
            style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)" }}
          >
            <div className="bsg-row" style={{ display: "contents" }}>
              <SummaryStat label="Games" value={String(result.n)} />
              <SummaryStat
                label="Brier"
                value={result.brier_score != null ? result.brier_score.toFixed(4) : "—"}
                color={
                  result.brier_score == null
                    ? "var(--text-3)"
                    : result.brier_score < 0.25
                    ? "var(--green)"
                    : result.brier_score > 0.25
                    ? "var(--red)"
                    : "var(--amber)"
                }
                term="brier-score"
              />
              <SummaryStat
                label="Flat P&L"
                value={`${flatTotal >= 0 ? "+" : ""}${flatTotal.toFixed(2)}u`}
                color={flatTotal >= 0 ? "var(--green)" : "var(--red)"}
              />
              <SummaryStat
                label="Kelly P&L"
                value={`${kellyTotal >= 0 ? "+" : ""}${kellyTotal.toFixed(2)}u`}
                color={kellyTotal >= 0 ? "var(--green)" : "var(--red)"}
                term="uncertainty-kelly"
              />
            </div>
          </div>

          <ChartFrame title="Calibration" term="calibration">
            <CalibrationChart buckets={result.calibration} />
          </ChartFrame>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
            <ChartFrame title="Tier hit rate" term="tiers">
              <TierHitRateChart rows={result.tier_hit_rates} />
            </ChartFrame>
            <ChartFrame title="Brier vs coin flip" term="brier-score">
              <BrierReadout brier={result.brier_score} />
            </ChartFrame>
          </div>

          <ChartFrame title="Cumulative P&L — flat vs Kelly">
            <PLLineChart flat={result.flat_pnl} kelly={result.kelly_pnl} />
          </ChartFrame>

          <ChartFrame title="Kelly bankroll" term="expected-log-growth">
            <KellyBankrollChart bankroll={result.kelly_bankroll} />
          </ChartFrame>

          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "10px",
              color: "var(--text-3)",
              lineHeight: 1.6,
              paddingLeft: "8px",
              borderLeft: "2px solid var(--clay)",
            }}
          >
            Replay basis: model re-run as-of each game date against final scores already in the DB.
            P&amp;L counts only games carrying a HOME/AWAY lean; flat stakes 1 unit, Kelly stakes the
            uncertainty-adjusted fraction. Past replay performance does not establish future results.
          </div>
        </div>
      )}
    </div>
  );
}
