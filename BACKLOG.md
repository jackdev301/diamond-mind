# Post-Slate Backlog

Changes and improvements to make after today's slate (2026-05-16) is complete.

---

## Model Fixes

### ~~Rebalance bullpen vs SP component weights~~ ✅ Done 2026-05-17
**Context:** KC @ STL — model picked KC (STRONG LEAN) because STL bullpen vulnerability (74/100)
outweighed STL's clear SP edge (Leahy FIP 4.74 vs Cameron 5.38). STL won 4-2.
**Fix applied:**
- Lowered `BULLPEN_VULN_SCALE` 0.0012 → 0.0009 (global 25% reduction)
- Added SP dominance gate: if either starter FIP < 4.0, bullpen weight × 0.55
- KC@STL ratio now 2.3x (was 4x). Ace starts flip ratio to 0.6x (SP dominates)

---

## Infrastructure

### Auto-settle postgame picks
Run a postgame script that fetches final scores from the MLB API and automatically
settles all pending BetRecords. Currently manual.

### Calibration reporting
Once enough settled results exist, add an endpoint/page showing:
- Win rate by tier (STRONG LEAN vs LEAN)
- ROI by market (ML vs O/U)
- Which component scores correlate with actual wins

---

## Notes

Add notes here during the day as games play out.

