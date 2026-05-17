const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Admin token — stored in localStorage, sent as X-Admin-Token on mutations.
// ---------------------------------------------------------------------------
export function getAdminToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("admin_token") ?? "";
}

export function setAdminToken(token: string): void {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("admin_token", token);
  } else {
    localStorage.removeItem("admin_token");
  }
}

function adminHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getAdminToken();
  return {
    ...(token ? { "X-Admin-Token": token } : {}),
    ...extra,
  };
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------
async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, { next: { revalidate: 60 } });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function post<T>(path: string, body: unknown): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function patch<T>(path: string, body: unknown): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

async function del(path: string): Promise<boolean> {
  try {
    const res = await fetch(`${API}${path}`, {
      method: "DELETE",
      headers: adminHeaders(),
    });
    return res.ok || res.status === 204;
  } catch {
    return false;
  }
}

export type Game = {
  game_id: number;
  game_date: string;
  home_team_id: number;
  away_team_id: number;
  home_team_abbr: string;
  away_team_abbr: string;
  venue: string;
  home_probable_starter_id: number | null;
  away_probable_starter_id: number | null;
};

export type BullpenData = {
  fatigue_score: number;
  overall_quality: number;
  available_quality: number;
  vulnerability_score: number;
  unavailable_relievers: string[];
  limited_relievers: string[];
  best_available: string[];
  betting_implication: string;
};

export type PitcherForm = {
  pitcher_name: string;
  era: number | null;
  whip: number | null;
  k_per_9: number | null;
  bb_per_9: number | null;
  hr_per_9: number | null;
  fip: number | null;
  babip: number | null;
  avg_pitches_per_start: number | null;
  trend_label: string;
  insufficient_sample: boolean;
};

export type GameBundle = {
  game_id: number;
  game_date: string;
  status: string;
  venue: string;
  home_team_id: number;
  away_team_id: number;
  home_team_abbr: string;
  away_team_abbr: string;
  home_form: Record<string, unknown> | null;
  away_form: Record<string, unknown> | null;
  home_starter: PitcherForm | null;
  away_starter: PitcherForm | null;
  home_bullpen: BullpenData | null;
  away_bullpen: BullpenData | null;
};

export type GameAnalysis = {
  game_id: number;
  home_team_abbr: string;
  away_team_abbr: string;
  model_home_win_prob: number;
  model_away_win_prob: number;
  ml_lean: string;
  ml_confidence: number;
  ml_tier: string;
  total_lean: string;
  total_tier: string;
  total_confidence: number;
  projected_total: number;
  total_line: number | null;
  total_kelly_fraction: number;
  qt_edge_quant: number;
  qt_edge_sd: number;
  qt_prob_positive: number;
  qt_p_model: number;
  qt_p_shrunk: number;
  qt_kelly_sized: number;
  qt_kelly_mult: number;
  qt_growth_rate: number;
  ml_kelly_fraction: number;
  key_factors: string[];
  cautions: string[];
  sp_advantage: string;
  bullpen_edge: string;
  offense_edge: string;
  ml_american_odds: number;
  implied_prob: number;
  vig_free_implied: number;
  overround: number;
  edge_vig_free: number;
  ev_per_dollar: number;
  component_fip: number;
  component_bullpen: number;
  component_offense: number;
  component_trend: number;
  component_k_matchup: number;
  component_weather: number;
  component_rest: number;
  component_park: number;
  // ── Quant layer (PhD-level) ──────────────────────────────
  q_prop_vig_free: number;   // proportional devig (Sonnet 4.6 theory)
  q_shin_vig_free: number;   // Shin devig (Opus 4.7)
  q_shin_z: number;          // estimated insider proportion
  q_p_model: number;
  q_p_shrunk: number;        // after Bayesian shrinkage to market
  q_shrink_weight: number;
  q_edge_naive: number;
  q_edge_quant: number;      // honest edge
  q_edge_sd: number;
  q_prob_positive: number;   // P(edge > 0)
  q_ci_low: number;
  q_ci_high: number;
  q_effective_n: number;
  q_kelly_full: number;
  q_kelly_sized: number;
  q_kelly_mult: number;      // derived multiplier
  q_growth_rate: number;     // expected log-growth per bet
  q_doubling_bets: number;   // 0 = never
  q_evidence_quality: number;
  // from picks endpoint
  game_date?: string;
  venue?: string;
};

export type TeamBatting = {
  estimated_woba: number | null;
  iso: number | null;
  strikeout_rate: number | null;
  walk_rate: number | null;
  ops: number | null;
  batting_avg: number | null;
  on_base_pct: number | null;
  slugging_pct: number | null;
  stolen_bases: number;
  caught_stealing: number;
  stolen_base_success_rate: number | null;
  games: number;
  insufficient_sample: boolean;
};

export type WeatherData = {
  temperature_f: number | null;
  wind_speed_mph: number | null;
  wind_direction_deg: number | null;
  precipitation_chance: number | null;
  is_dome: boolean;
};

/** Returned by /games/{id}/context — bundle + weather + analysis in one call. */
export type GameContext = {
  game_id: number;
  game_date: string;
  status: string;
  venue: string;
  home_team_id: number;
  away_team_id: number;
  home_team_abbr: string;
  away_team_abbr: string;
  home_form: Record<string, unknown> | null;
  away_form: Record<string, unknown> | null;
  home_starter: PitcherForm | null;
  away_starter: PitcherForm | null;
  home_bullpen: BullpenData | null;
  away_bullpen: BullpenData | null;
  weather: WeatherData | null;
  analysis: GameAnalysis | null;
};

/** Returned by /games/slate — one entry per game, everything bundled. */
export type SlateGame = {
  game_id: number;
  game_date: string;
  status: string;
  venue: string;
  home_team_id: number;
  home_team_abbr: string;
  away_team_id: number;
  away_team_abbr: string;
  home_probable_starter_id: number | null;
  away_probable_starter_id: number | null;
  home_bullpen: BullpenData | null;
  away_bullpen: BullpenData | null;
  analysis: GameAnalysis | null;
};

export const api = {
  games: (date: string) => get<Game[]>(`/games?game_date=${date}`),
  slate: (date: string) => get<SlateGame[]>(`/games/slate?game_date=${date}`),
  bundle: (gameId: number, asOf: string) => get<GameBundle>(`/games/${gameId}/bundle?as_of=${asOf}`),
  weather: (gameId: number) => get<WeatherData>(`/games/${gameId}/weather`),
  odds: (gameId: number) => get<unknown[]>(`/games/${gameId}/odds`),
  bullpen: (teamId: number, date: string) =>
    get<BullpenData>(`/teams/${teamId}/bullpen?as_of=${date}`),
  pitcher: (id: number, asOf: string) => get<PitcherForm>(`/pitchers/${id}/form?as_of=${asOf}`),
  polishReport: (markdown: string) =>
    post<{ markdown: string; polished: boolean; method: "sdk" | "cli" | "none" }>("/report/polish", { markdown }),
  analyze: (gameId: number, asOf: string) =>
    get<GameAnalysis>(`/games/${gameId}/analyze?as_of=${asOf}`),
  picks: (date: string) =>
    get<GameAnalysis[]>(`/games/picks?game_date=${date}`),
  batting: (teamId: number, date: string) =>
    get<TeamBatting>(`/teams/${teamId}/batting?as_of=${date}&window=l10`),
  context: (gameId: number, asOf: string) =>
    get<GameContext>(`/games/${gameId}/context?as_of=${asOf}`),
  reportMarkdown: async (date: string): Promise<string | null> => {
    try {
      const res = await fetch(`${API}/report?date=${date}`);
      if (!res.ok) return null;
      return res.text();
    } catch {
      return null;
    }
  },
  quantVerify: (modelProb: number, sideOdds: number, otherOdds: number, evidence: number) =>
    get<QuantVerify>(
      `/quant/verify?model_prob=${modelProb}&side_odds=${sideOdds}&other_odds=${otherOdds}&evidence_quality=${evidence}`,
    ),
  // ── Tracker ──────────────────────────────────────────────────────────────
  trackerBets: (params?: { date_from?: string; date_to?: string; market?: string }) => {
    const qs = new URLSearchParams();
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.market) qs.set("market", params.market);
    const q = qs.toString();
    return get<BetRecord[]>(`/tracker/bets${q ? "?" + q : ""}`);
  },
  trackerCreateBet: (payload: BetCreatePayload) =>
    post<BetRecord>("/tracker/bets", payload),
  trackerSettleBet: (id: number, result: "WIN" | "LOSS" | "PUSH", units_returned?: number) =>
    patch<BetRecord>(`/tracker/bets/${id}`, { result, units_returned }),
  trackerDeleteBet: (id: number) => del(`/tracker/bets/${id}`),
  trackerSummary: (params?: { date_from?: string; date_to?: string }) => {
    const qs = new URLSearchParams();
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    const q = qs.toString();
    return get<TrackerSummary>(`/tracker/summary${q ? "?" + q : ""}`);
  },
  trackerAutoTrack: (date: string) =>
    post<{ created: number; skipped: number; date: string }>(
      `/tracker/auto-track?game_date=${date}`,
      {},
    ),
  adminRunIngestion: (date: string) =>
    post<{ job_id: string; as_of: string; status: string }>(
      `/admin/run-ingestion?game_date=${date}`,
      {},
    ),
  adminIngestionStatus: (jobId: string, tail?: number) =>
    get<{
      job_id: string;
      status: string;
      started_at: string;
      as_of: string;
      error: string | null;
      log_lines_total: number;
      log_tail: string[];
    }>(`/admin/ingestion-status/${jobId}${tail ? `?tail=${tail}` : ""}`),
  adminIngestionJobs: () =>
    get<
      Array<{
        job_id: string;
        status: string;
        started_at: string;
        as_of: string;
        log_lines_total: number;
        error: string | null;
      }>
    >(`/admin/ingestion-jobs`),
};

export type QuantVerify = {
  prop_vig_free: number;
  shin_vig_free: number;
  shin_z: number;
  booksum: number;
  p_model: number;
  p_shrunk: number;
  shrink_weight: number;
  edge_naive: number;
  edge_quant: number;
  edge_sd: number;
  prob_positive: number;
  ci_low: number;
  ci_high: number;
  effective_n: number;
  kelly_full: number;
  kelly_sized: number;
  kelly_multiplier: number;
  growth_rate: number;
  doubling_bets: number | null;
  ev_per_dollar: number;
  recommendation: string;
};

// ── Tracker types ──────────────────────────────────────────────────────────

export type BetRecord = {
  id: number;
  game_id: number;
  game_date: string;
  market: "moneyline" | "total";
  selection: string;
  american_odds: number;
  units: number;
  result: "WIN" | "LOSS" | "PUSH" | null;
  units_returned: number | null;
  tier: string;
  home_team_abbr: string;
  away_team_abbr: string;
  total_line: number | null;
  projected_total: number | null;
  created_at: string | null;
};

export type BetCreatePayload = {
  game_id: number;
  game_date: string;
  market: "moneyline" | "total";
  selection: string;
  american_odds: number;
  units?: number;
  tier: string;
  home_team_abbr: string;
  away_team_abbr: string;
  total_line?: number | null;
  projected_total?: number | null;
};

export type TrackerSummaryGroup = {
  bets: number;
  wins: number;
  losses: number;
  pushes: number;
  pending: number;
  units_wagered: number;
  units_net: number;
};

export type TrackerSummary = {
  ml: TrackerSummaryGroup;
  total: TrackerSummaryGroup;
  combined: TrackerSummaryGroup;
};
