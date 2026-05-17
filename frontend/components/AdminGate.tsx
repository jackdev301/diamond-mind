"use client";

/**
 * AdminGate — a small lock/unlock widget.
 *
 * Usage:
 *   <AdminGate onUnlocked={() => setUnlocked(true)} />
 *
 * Shows a 🔒 button. Clicking it opens a password prompt; on success it
 * stores the token in localStorage via api.setAdminToken() and calls
 * onUnlocked(). While locked, mutating UI should be hidden or disabled.
 */

import { useState } from "react";
import { getAdminToken, setAdminToken } from "@/lib/api";

interface Props {
  onUnlocked?: () => void;
}

export default function AdminGate({ onUnlocked }: Props) {
  const [unlocked, setUnlocked] = useState(() => Boolean(getAdminToken()));
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");

  function handleUnlock() {
    if (!input.trim()) {
      setError("Enter the admin token.");
      return;
    }
    setAdminToken(input.trim());
    setUnlocked(true);
    setOpen(false);
    setInput("");
    setError("");
    onUnlocked?.();
  }

  function handleLock() {
    setAdminToken("");
    setUnlocked(false);
  }

  return (
    <>
      <button
        onClick={unlocked ? handleLock : () => setOpen(true)}
        title={unlocked ? "Lock admin actions" : "Unlock admin actions"}
        className={`text-xs px-2 py-1 rounded border font-mono transition-colors ${
          unlocked
            ? "border-emerald-500 text-emerald-400 hover:bg-emerald-900/30"
            : "border-zinc-600 text-zinc-400 hover:border-zinc-400 hover:text-zinc-200"
        }`}
      >
        {unlocked ? "🔓 admin" : "🔒 locked"}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-6 w-80 shadow-xl">
            <h2 className="text-sm font-semibold text-zinc-100 mb-1">Admin unlock</h2>
            <p className="text-xs text-zinc-400 mb-4">
              Enter the admin token to enable settle / delete actions.
            </p>
            <input
              type="password"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
              placeholder="Token"
              className="w-full bg-zinc-800 border border-zinc-600 rounded px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-zinc-400 mb-2"
            />
            {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => { setOpen(false); setInput(""); setError(""); }}
                className="text-xs px-3 py-1.5 rounded border border-zinc-600 text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                onClick={handleUnlock}
                className="text-xs px-3 py-1.5 rounded bg-zinc-700 text-zinc-100 hover:bg-zinc-600 font-medium"
              >
                Unlock
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
