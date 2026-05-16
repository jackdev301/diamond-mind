"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, type GameBundle, type WeatherData } from "@/lib/api";

function StatRow({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex justify-between py-1 border-b border-gray-800 text-sm">
      <span className="text-gray-400">{label}</span>
      <span className="font-medium">{value ?? "—"}</span>
    </div>
  );
}

function BullpenCard({ abbr, bp }: { abbr: string; bp: NonNullable<GameBundle["home_bullpen"]> }) {
  const vulnColor = bp.vulnerability_score >= 70 ? "text-red-400" : bp.vulnerability_score >= 50 ? "text-orange-400" : "text-green-400";
  return (
    <div className="border border-gray-800 rounded-lg p-4">
      <h3 className="font-bold mb-3">{abbr} Bullpen</h3>
      <StatRow label="Vulnerability" value={<span className={vulnColor}>{bp.vulnerability_score}/100</span> as unknown as string} />
      <StatRow label="Fatigue" value={`${bp.fatigue_score}/100`} />
      <StatRow label="Overall Quality" value={`${bp.overall_quality}/100`} />
      <StatRow label="Available Quality" value={`${bp.available_quality}/100`} />
      {(bp.unavailable_relievers?.length ?? 0) > 0 && (
        <p className="text-red-400 text-xs mt-2">Unavailable: {bp.unavailable_relievers.join(", ")}</p>
      )}
      {(bp.limited_relievers?.length ?? 0) > 0 && (
        <p className="text-orange-400 text-xs mt-1">Limited: {bp.limited_relievers.join(", ")}</p>
      )}
      {(bp.best_available?.length ?? 0) > 0 && (
        <p className="text-green-400 text-xs mt-1">Best available: {bp.best_available.join(", ")}</p>
      )}
      <p className="text-gray-500 text-xs mt-3 italic">{bp.betting_implication}</p>
    </div>
  );
}

function WeatherCard({ w }: { w: WeatherData }) {
  if (w.is_dome) return (
    <div className="border border-gray-800 rounded-lg p-4">
      <h3 className="font-bold mb-2">Weather</h3>
      <p className="text-gray-400 text-sm">Indoor venue — weather not a factor.</p>
    </div>
  );
  const dir = w.wind_direction_deg != null ? `${w.wind_direction_deg}°` : "—";
  return (
    <div className="border border-gray-800 rounded-lg p-4">
      <h3 className="font-bold mb-3">Weather</h3>
      <StatRow label="Temperature" value={w.temperature_f != null ? `${w.temperature_f}°F` : null} />
      <StatRow label="Wind" value={w.wind_speed_mph != null ? `${w.wind_speed_mph} mph @ ${dir}` : null} />
      <StatRow label="Precip Chance" value={w.precipitation_chance != null ? `${w.precipitation_chance}%` : null} />
    </div>
  );
}

export default function GameDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [bundle, setBundle] = useState<GameBundle | null>(null);
  const [weather, setWeather] = useState<WeatherData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const gameId = Number(id);
    const today = new Date().toISOString().split("T")[0];
    api.bundle(gameId, today).then((b) => { setBundle(b); setLoading(false); });
    api.weather(gameId).then((w) => setWeather(w));
  }, [id]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (!bundle) return <p className="text-red-400">Game not found.</p>;

  return (
    <div>
      <Link href="/" className="text-gray-500 text-sm hover:text-white mb-4 inline-block">← Slate</Link>
      <h1 className="text-2xl font-bold mb-1">
        {bundle.away_team_abbr} @ {bundle.home_team_abbr}
      </h1>
      <p className="text-gray-500 text-sm mb-6">{bundle.venue} · {bundle.game_date}</p>

      {/* Starters */}
      <h2 className="text-lg font-semibold mb-3">Starting Pitchers</h2>
      <div className="grid grid-cols-2 gap-4 mb-8">
        {[
          { role: "home", abbr: bundle.home_team_abbr, starter: bundle.home_starter },
          { role: "away", abbr: bundle.away_team_abbr, starter: bundle.away_starter },
        ].map(({ role, abbr, starter }) => (
          <div key={role} className="border border-gray-800 rounded-lg p-4">
            <h3 className="font-bold mb-3">{abbr}</h3>
            {starter ? (
              <>
                <p className="text-sm mb-2">{starter.pitcher_name}</p>
                <StatRow label="ERA" value={starter.era?.toFixed(2)} />
                <StatRow label="WHIP" value={starter.whip?.toFixed(2)} />
                <StatRow label="K/9" value={starter.k_per_9?.toFixed(1)} />
                <StatRow label="Trend" value={starter.trend_label?.replace(/_/g, " ")} />
                {starter.insufficient_sample && (
                  <p className="text-yellow-500 text-xs mt-2">⚠ Small sample</p>
                )}
              </>
            ) : (
              <p className="text-gray-500 text-sm">TBD</p>
            )}
          </div>
        ))}
      </div>

      {/* Bullpens */}
      <h2 className="text-lg font-semibold mb-3">Bullpen Intelligence</h2>
      <div className="grid grid-cols-2 gap-4 mb-8">
        {bundle.home_bullpen && <BullpenCard abbr={bundle.home_team_abbr} bp={bundle.home_bullpen} />}
        {bundle.away_bullpen && <BullpenCard abbr={bundle.away_team_abbr} bp={bundle.away_bullpen} />}
      </div>

      {/* Weather */}
      {weather && (
        <>
          <h2 className="text-lg font-semibold mb-3">Conditions</h2>
          <WeatherCard w={weather} />
        </>
      )}
    </div>
  );
}
