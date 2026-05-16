// Maps our DB abbreviations to ESPN's team logo slug.
// ESPN CDN: https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png
const ABBR_TO_ESPN: Record<string, string> = {
  ARI: "ari", ATL: "atl", BAL: "bal", BOS: "bos",
  CHC: "chc", CWS: "chw", CIN: "cin", CLE: "cle",
  COL: "col", DET: "det", HOU: "hou", KC:  "kc",
  LAA: "laa", LAD: "lad", MIA: "mia", MIL: "mil",
  MIN: "min", NYM: "nym", NYY: "nyy", OAK: "oak",
  PHI: "phi", PIT: "pit", SD:  "sd",  SEA: "sea",
  SF:  "sf",  STL: "stl", TB:  "tb",  TEX: "tex",
  TOR: "tor", WSH: "wsh",
};

export function teamLogoUrl(abbr: string, size: 40 | 60 | 80 | 120 = 60): string {
  const slug = ABBR_TO_ESPN[abbr] ?? abbr.toLowerCase();
  return `https://a.espncdn.com/i/teamlogos/mlb/500/${slug}.png`;
}
