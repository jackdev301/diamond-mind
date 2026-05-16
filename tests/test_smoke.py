"""Phase 2 smoke tests — verify the skeleton imports and config loads."""

from datetime import date

from app import __version__
from app.config import Settings
from app.contracts import TeamFormWindow, TrendLabel, WindowKey


def test_package_version():
    assert __version__ == "0.1.0"


def test_settings_load_with_no_env_file(monkeypatch, tmp_path):
    # Disable .env so we exercise pure defaults.
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("sqlite")
    assert settings.has_odds_api is False
    assert settings.has_openweather is False
    assert settings.has_anthropic is False


def test_database_engine_constructs():
    from app.database import engine
    assert engine is not None


def test_contract_dataclass_constructs():
    window = TeamFormWindow(
        team_id=1,
        team_abbr="PHI",
        window=WindowKey.L10,
        games=10,
        runs_per_game=4.8,
        runs_allowed_per_game=3.9,
        team_ops=0.742,
        record_wins=6,
        record_losses=4,
        trend_label=TrendLabel.HEATING_UP,
        as_of_date=date(2026, 5, 15),
    )
    assert window.team_abbr == "PHI"
    assert window.trend_label is TrendLabel.HEATING_UP
    assert window.insufficient_sample is False
