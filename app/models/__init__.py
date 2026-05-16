"""ORM model registry.

Importing this package side-effects all models onto `Base.metadata`, which
is what `Base.metadata.create_all(engine)` needs to actually emit DDL.
Track B should NOT import these directly — use the dataclasses in
`app.contracts` and the query helpers (Phase 5) instead.
"""

from app.models.entities import Player, Team
from app.models.games import (
    Game,
    PitcherGameLog,
    PlayerGameLog,
    TeamGameLog,
)
from app.models.players import (
    PitcherFormWindowRow,
    PlayerFormWindowRow,
    RelieverFormWindowRow,
    TeamFormWindowRow,
)
from app.models.bullpen import BullpenFatigueRow, RelieverUsageRow
from app.models.odds import OddsSnapshotRow, WeatherSnapshotRow
from app.models.reports import BetEvaluationRow, ModelRun, ObsidianExportRow

__all__ = [
    "Team",
    "Player",
    "Game",
    "TeamGameLog",
    "PlayerGameLog",
    "PitcherGameLog",
    "TeamFormWindowRow",
    "PlayerFormWindowRow",
    "PitcherFormWindowRow",
    "RelieverFormWindowRow",
    "RelieverUsageRow",
    "BullpenFatigueRow",
    "OddsSnapshotRow",
    "WeatherSnapshotRow",
    "ModelRun",
    "BetEvaluationRow",
    "ObsidianExportRow",
]
