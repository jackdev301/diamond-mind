"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Game, type BullpenData } from "@/lib/api";

function vulnColor(score: number) {
  if (score >= 70) return "text-red-400";
  if (score >= 50) return "text-orange-400";
  return "text-green-400";
}

function GameCard({ game, date }: { game: Game; date: string }) {
  const [homeBp, setHomeBp] = useState<BullpenData | null>(null);
  const [awayBp, setAwayBp] = useState<BullpenData | null>(null);

  useEffect(() => {
    api.bullpen(game.home_team_id, date).then(setHomeBp);
    api.bullpen(game.away_team_id, date).then(setAwayBp);
  }, [game, date]);

  return (
    <Link href={`/game/${game.game_id}`}>
      <div className="border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="font-bold text-lg">{game.away_team_abbr} @ {game.home_team_abbr}</h2>
            <p className="text-gray-500 text-sm">{game.venue}</p>
          </div>
          <div className="text-right space-y-1 text-sm font-semibold">
            {awayBp && <div className={vulnColor(awayBp.vulnerability_score)}>{game.away_team_abbr} vuln: {awayBp.vulnerability_score}/100</div>}
            {homeBp && <div className={vulnColor(homeBp.vulnerability_score)}>{game.home_team_abbr} vuln: {homeBp.vulnerability_score}/100</div>}
          </div>
        </div>
        {homeBp && <p className="text-gray-600 text-xs mt-2 italic">{homeBp.betting_implication}</p>}
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
    setGames(null); setError(false);
    api.games(date).then((g) => { if (g === null) setError(true); else setGames(g); });
  }, [date]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Today's Slate</h1>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
          className="bg-gray-900 border border-gray-700 rounded px-3 py-1 text-sm" />
      </div>
      {error && <p className="text-red-400 text-sm">Backend not reachable — run: <code className="bg-gray-900 px-1 rounded">uvicorn app.api.routes:app --reload --port 8000</code></p>}
      {!error && games === null && <p className="text-gray-500">Loading...</p>}
      {games?.length === 0 && <p className="text-gray-500">No games for {date}.</p>}
      <div className="space-y-3">
        {games?.map((g) => <GameCard key={g.game_id} game={g} date={date} />)}
      </div>
    </div>
  );
}
