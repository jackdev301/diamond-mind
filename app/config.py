"""Runtime configuration loaded from environment / .env file.

Missing API keys are not fatal — clients should stub gracefully and the
generated report should flag the data gap. See `.env.example` for the
full set of variables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(default="sqlite:///./diamond_mind.db")

    mlb_stats_api_base: str = Field(default="https://statsapi.mlb.com/api/v1")

    odds_api_key: Optional[str] = None
    odds_api_base: str = Field(default="https://api.the-odds-api.com/v4")
    preferred_bookmaker: str = Field(default="draftkings")

    # DraftKings direct API (not yet public — stub for when it is)
    draftkings_api_key: Optional[str] = None

    weather_provider: str = Field(default="open-meteo")
    openweather_api_key: Optional[str] = None

    obsidian_vault_path: Path = Field(default=PROJECT_ROOT / "obsidian_vault")

    anthropic_api_key: Optional[str] = None

    log_level: str = Field(default="INFO")

    @property
    def has_odds_api(self) -> bool:
        return bool(self.odds_api_key)

    @property
    def has_openweather(self) -> bool:
        return bool(self.openweather_api_key)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


def get_settings() -> Settings:
    return Settings()
