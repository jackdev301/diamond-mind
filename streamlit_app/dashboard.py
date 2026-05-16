"""Diamond Mind — Streamlit Dashboard

Run with:
    streamlit run streamlit_app/dashboard.py

Expects the FastAPI backend running on localhost:8000:
    uvicorn app.api.routes:app --reload --port 8000
"""

import json
import urllib.request
import urllib.error
from datetime import date

import streamlit as st

API = "http://localhost:8000"


def _get(path: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=5) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


def _post(path: str, body: dict) -> dict | None:
    try:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{API}{path}", data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Diamond Mind",
    page_icon="⚾",
    layout="wide",
)

st.title("⚾ Diamond Mind — MLB Intelligence")

health = _get("/health")
if not health:
    st.error("Backend not reachable — start the API with: `uvicorn app.api.routes:app --reload --port 8000`")
    st.stop()

# ── Sidebar nav ───────────────────────────────────────────────────────────────

page = st.sidebar.radio(
    "Navigate",
    ["Slate", "Game Detail", "Report Viewer", "Bet Verifier"],
)

today = str(date.today())


# ── SLATE ─────────────────────────────────────────────────────────────────────

if page == "Slate":
    st.header("Today's Slate")

    game_date = st.sidebar.date_input("Date", value=date.today())
    games = _get(f"/games?date={game_date}") or []

    if not games:
        st.info("No games found for this date. Check the date or run the pregame update.")
        st.stop()

    for g in games:
        home = g.get("home_team_abbr", "?")
        away = g.get("away_team_abbr", "?")

        home_bp = _get(f"/teams/{g['home_team_id']}/bullpen?date={game_date}") or {}
        away_bp = _get(f"/teams/{g['away_team_id']}/bullpen?date={game_date}") or {}

        home_vuln = home_bp.get("vulnerability_score", "—")
        away_vuln = away_bp.get("vulnerability_score", "—")

        def _vuln_color(v):
            if not isinstance(v, (int, float)):
                return "gray"
            if v >= 70: return "red"
            if v >= 50: return "orange"
            return "green"

        with st.container():
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                st.subheader(f"{away} @ {home}")
                st.caption(g.get("venue", ""))
            with col2:
                st.metric(f"{away} Bullpen Vuln", f"{away_vuln}/100" if isinstance(away_vuln, (int, float)) else away_vuln)
            with col3:
                st.metric(f"{home} Bullpen Vuln", f"{home_vuln}/100" if isinstance(home_vuln, (int, float)) else home_vuln)
            st.divider()


# ── GAME DETAIL ───────────────────────────────────────────────────────────────

elif page == "Game Detail":
    st.header("Game Detail")

    game_date = st.sidebar.date_input("Date", value=date.today())
    games = _get(f"/games?date={game_date}") or []

    if not games:
        st.info("No games found.")
        st.stop()

    options = {f"{g['away_team_abbr']} @ {g['home_team_abbr']}": g for g in games}
    selection = st.selectbox("Select game", list(options.keys()))
    g = options[selection]

    home_id, away_id = g["home_team_id"], g["away_team_id"]
    home, away = g["home_team_abbr"], g["away_team_abbr"]

    st.subheader(f"{away} @ {home} — {g.get('venue', '')}")

    # Starters
    st.markdown("### Starting Pitchers")
    col1, col2 = st.columns(2)
    for col, team, pid_key in [(col1, home, "home_probable_starter_id"), (col2, away, "away_probable_starter_id")]:
        with col:
            st.markdown(f"**{team}**")
            pid = g.get(pid_key)
            if pid:
                form = _get(f"/pitchers/{pid}/form") or {}
                if form:
                    st.metric("ERA", f"{form.get('era', '—'):.2f}" if isinstance(form.get('era'), float) else "—")
                    st.metric("WHIP", f"{form.get('whip', '—'):.2f}" if isinstance(form.get('whip'), float) else "—")
                    st.caption(f"Trend: {form.get('trend_label', '—')}")
                else:
                    st.caption("No form data")
            else:
                st.caption("TBD")

    # Bullpens
    st.markdown("### Bullpen Intelligence")
    col1, col2 = st.columns(2)
    for col, abbr, tid in [(col1, home, home_id), (col2, away, away_id)]:
        with col:
            bp = _get(f"/teams/{tid}/bullpen?date={game_date}") or {}
            st.markdown(f"**{abbr}**")
            if bp:
                st.metric("Vulnerability", f"{bp.get('vulnerability_score', '—')}/100")
                st.metric("Fatigue", f"{bp.get('fatigue_score', '—')}/100")
                st.metric("Available Quality", f"{bp.get('available_quality', '—')}/100")
                if bp.get("unavailable_relievers"):
                    st.warning(f"Unavailable: {', '.join(bp['unavailable_relievers'])}")
                if bp.get("limited_relievers"):
                    st.info(f"Limited: {', '.join(bp['limited_relievers'])}")
                st.caption(bp.get("betting_implication", ""))
            else:
                st.caption("No bullpen data")


# ── REPORT VIEWER ─────────────────────────────────────────────────────────────

elif page == "Report Viewer":
    st.header("Daily Report")

    report_date = st.sidebar.date_input("Date", value=date.today())
    report_path = f"obsidian_vault/Reports/Daily/{report_date}.md"

    try:
        with open(report_path, encoding="utf-8") as f:
            raw = f.read()
        st.markdown(raw)

        if st.button("Polish with Claude"):
            with st.spinner("Polishing report..."):
                result = _post("/report/polish", {"markdown": raw})
            if result and "polished" in result:
                st.markdown("---")
                st.markdown("### Polished Report")
                st.markdown(result["polished"])
            else:
                st.error("Polish failed — check ANTHROPIC_API_KEY in .env")
    except FileNotFoundError:
        st.info(f"No report found for {report_date}. Run `python scripts/run_daily_report.py` first.")


# ── BET VERIFIER ──────────────────────────────────────────────────────────────

elif page == "Bet Verifier":
    st.header("Bet Verifier")
    st.caption("Verify a market edge — cautious tiers only. Not financial advice.")

    col1, col2 = st.columns(2)
    with col1:
        american_odds = st.number_input("American Odds (e.g. -150 or +130)", value=-110, step=5)
        model_prob = st.slider("Your estimated probability", 0.01, 0.99, 0.50, 0.01)
    with col2:
        confidence = st.slider("Confidence in estimate", 0.0, 1.0, 0.6, 0.05)
        evidence_quality = st.slider("Evidence quality", 0.0, 1.0, 0.6, 0.05)

    if st.button("Evaluate"):
        from app.betting.implied_probability import implied_probability
        from app.betting.edge_calculator import edge, recommendation

        impl_prob = implied_probability(american_odds)
        edge_val = edge(model_prob, american_odds)
        rec = recommendation(edge_val, confidence, evidence_quality)

        st.markdown("### Result")
        col1, col2, col3 = st.columns(3)
        col1.metric("Implied Probability", f"{impl_prob:.1%}")
        col2.metric("Edge", f"{edge_val:+.1%}")
        col3.metric("Recommendation", rec.replace("_", " ").title())

        if rec == "strong_lean":
            st.success("Strong Lean — meaningful edge with solid confidence.")
        elif rec == "lean":
            st.info("Lean — modest edge, proceed with caution.")
        elif rec == "avoid":
            st.error("Avoid — negative edge.")
        elif rec == "need_more_info":
            st.warning("Need More Info — confidence or evidence quality too low.")
        else:
            st.info("Pass — no meaningful edge detected.")
