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
  era: number;
  whip: number;
  k_per_9: number;
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

export const api = {
  games: (date: string) => get<Game[]>(`/games?date=${date}`),
  bundle: (gameId: number) => get<GameBundle>(`/games/${gameId}/bundle`),
  bullpen: (teamId: number, date: string) =>
    get<BullpenData>(`/teams/${teamId}/bullpen?date=${date}`),
  pitcher: (id: number) => get<PitcherForm>(`/pitchers/${id}/form`),
  polishReport: (markdown: string) =>
    post<{ polished: string }>("/report/polish", { markdown }),
};
