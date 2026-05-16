"use client";

import { useState } from "react";

function impliedProbability(odds: number): number {
  if (odds < 0) return Math.abs(odds) / (Math.abs(odds) + 100);
  return 100 / (odds + 100);
}

function recommendation(edge: number, confidence: number, evidenceQuality: number): string {
  if (confidence < 0.4 || evidenceQuality < 0.4) return "Need More Info";
  if (edge >= 0.06 && confidence >= 0.7 && evidenceQuality >= 0.7) return "Strong Lean";
  if (edge >= 0.03 && confidence >= 0.55) return "Lean";
  if (edge <= -0.05) return "Avoid";
  return "Pass";
}

function recColor(rec: string) {
  if (rec === "Strong Lean") return "text-green-400";
  if (rec === "Lean") return "text-blue-400";
  if (rec === "Avoid") return "text-red-400";
  if (rec === "Need More Info") return "text-yellow-400";
  return "text-gray-400";
}

export default function VerifyPage() {
  const [odds, setOdds] = useState(-110);
  const [modelProb, setModelProb] = useState(0.5);
  const [confidence, setConfidence] = useState(0.6);
  const [evidenceQuality, setEvidenceQuality] = useState(0.6);
  const [result, setResult] = useState<{ impliedProb: number; edge: number; rec: string } | null>(null);

  function evaluate() {
    const impliedProb = impliedProbability(odds);
    const edge = modelProb - impliedProb;
    const rec = recommendation(edge, confidence, evidenceQuality);
    setResult({ impliedProb, edge, rec });
  }

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold mb-2">Bet Verifier</h1>
      <p className="text-gray-500 text-sm mb-6">
        Cautious tiers only: Strong Lean / Lean / Pass / Avoid / Need More Info. Not financial advice.
      </p>

      <div className="space-y-5">
        <div>
          <label className="block text-sm text-gray-400 mb-1">American Odds (e.g. -150 or +130)</label>
          <input type="number" value={odds} onChange={(e) => setOdds(Number(e.target.value))} step={5}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm" />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Your estimated probability: {(modelProb * 100).toFixed(0)}%</label>
          <input type="range" min={0.01} max={0.99} step={0.01} value={modelProb}
            onChange={(e) => setModelProb(Number(e.target.value))} className="w-full" />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Confidence in estimate: {(confidence * 100).toFixed(0)}%</label>
          <input type="range" min={0} max={1} step={0.05} value={confidence}
            onChange={(e) => setConfidence(Number(e.target.value))} className="w-full" />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Evidence quality: {(evidenceQuality * 100).toFixed(0)}%</label>
          <input type="range" min={0} max={1} step={0.05} value={evidenceQuality}
            onChange={(e) => setEvidenceQuality(Number(e.target.value))} className="w-full" />
        </div>

        <button onClick={evaluate}
          className="w-full bg-indigo-700 hover:bg-indigo-600 py-2 rounded font-medium transition-colors">
          Evaluate
        </button>
      </div>

      {result && (
        <div className="mt-6 border border-gray-800 rounded-lg p-4 space-y-3">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Implied Probability</span>
            <span>{(result.impliedProb * 100).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Your Estimate</span>
            <span>{(modelProb * 100).toFixed(1)}%</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Edge</span>
            <span className={result.edge >= 0 ? "text-green-400" : "text-red-400"}>
              {result.edge >= 0 ? "+" : ""}{(result.edge * 100).toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between text-sm font-bold border-t border-gray-800 pt-3">
            <span className="text-gray-400">Recommendation</span>
            <span className={recColor(result.rec)}>{result.rec}</span>
          </div>
        </div>
      )}
    </div>
  );
}
