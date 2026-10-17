"""Environment configuration, with no credentials embedded in code."""

from dataclasses import dataclass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    containers_file: Path = ROOT / "data" / "containers.json"
    scorer: str = "gate_triage.score:score"
    containers_per_lane_per_day: int = 12
    cors_origins: tuple[str, ...] = ("*",)
    cloud_reasoner: str | None = None
    reason_limit: int = 20

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            containers_file=Path(os.getenv("CONTAINERS_FILE", str(ROOT / "data" / "containers.json"))),
            scorer=os.getenv("SCORER", "gate_triage.score:score"),
            containers_per_lane_per_day=int(os.getenv("CONTAINERS_PER_LANE_PER_DAY", "12")),
            cors_origins=tuple(x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()),
            cloud_reasoner=os.getenv("CLOUD_REASONER") or None,
            reason_limit=int(os.getenv("LLM_REASON_LIMIT", "20")),
        )

    def __post_init__(self) -> None:
        if self.containers_per_lane_per_day < 1:
            raise ValueError("CONTAINERS_PER_LANE_PER_DAY must be positive")
        if not 1 <= self.reason_limit <= 20:
            raise ValueError("LLM_REASON_LIMIT must be between 1 and 20")
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
