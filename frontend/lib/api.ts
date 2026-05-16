const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
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
  total_confidence: number;
  projected_total: number;
  ml_kelly_fraction: number;
  key_factors: string[];
  cautions: string[];
  sp_advantage: string;
  bullpen_edge: string;
  offense_edge: string;
  ml_american_odds: number;
  implied_prob: number;
  component_fip: number;
  component_bullpen: number;
  component_offense: number;
  component_trend: number;
  component_k_matchup: number;
  component_weather: number;
  component_rest: number;
  component_park: number;
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

export const api = {
  games: (date: string) => get<Game[]>(`/games?game_date=${date}`),
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
};
