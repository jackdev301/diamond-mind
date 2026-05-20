"use client";

import { useState } from "react";
import { GlossaryPanel } from "@/components/glossary-panel";

/**
 * Persistent "?" affordance pinned to the right end of the nav bar. Owns the
 * open/closed state for the methodology drawer.
 */
export function GlossaryButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className="glossary-q-btn"
        aria-label="Open methodology and glossary"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        ?
      </button>
      <GlossaryPanel open={open} onClose={() => setOpen(false)} />
    </>
  );
}
