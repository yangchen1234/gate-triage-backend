"""Public request contracts; provider payloads stay inside the connector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkspaceCreate(StrictModel):
    mode: Literal["SIMULATION", "REPLAY_T49", "LIVE_T49"] = "SIMULATION"
    name: str = Field(default="LA terminal rehearsal", min_length=1, max_length=160)
    scenario_id: str = Field(default="battery_truck_access_2024", max_length=100)
    seed: int = Field(default=17, ge=0, le=2147483647)


class TaskEventCreate(StrictModel):
    task_id: str = Field(min_length=1, max_length=160)
    action: Literal["acknowledge", "start", "record_contact", "wait", "record_result"]
    result_code: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)


class PlanCreate(StrictModel):
    profile: Literal["throughput", "balanced", "recovery"] = "throughput"
    strategy: Literal["optimized", "fifo", "priority"] = "optimized"
    run_id: str | None = None
    input_revision: int | None = Field(default=None, ge=1)


class ExperimentCreate(StrictModel):
    scenario_id: str | None = Field(default=None, max_length=100)
    seeds: list[int] = Field(default_factory=lambda: [17, 29, 43], min_length=1, max_length=30)
    horizon_minutes: int = Field(default=240, ge=1, le=240)

    @field_validator("seeds")
    @classmethod
    def independent_seeds(cls, seeds: list[int]) -> list[int]:
        if any(seed < 0 or seed > 2147483647 for seed in seeds):
            raise ValueError("Seeds must be between 0 and 2147483647")
        if len(set(seeds)) != len(seeds):
            raise ValueError("Use distinct seeds for independent paired worlds")
        return seeds


class ExportCreate(StrictModel):
    subject_type: Literal["plan", "experiment", "handoff"] = "handoff"
    subject_id: str | None = Field(default=None, max_length=100)
    format: Literal["json", "csv", "html"] = "json"


class SimulationCreate(StrictModel):
    scenario_id: str
    scenario_version: str | None = None
    seed: int = Field(default=17, ge=0, le=2147483647)
    parameter_overrides: dict = Field(default_factory=dict)


class PlanSelection(StrictModel):
    plan_id: str
    input_revision: int = Field(ge=1)


class PlaybackChange(StrictModel):
    playing: bool
    speed: float = Field(default=1, ge=1, le=60)
    tick_minutes: int = Field(default=1, ge=1, le=5)
    strategy: Literal["optimized", "fifo", "priority"] = "optimized"
    profile: Literal["throughput", "balanced", "recovery"] = "throughput"


class CoordinationRequestCreate(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    owner_role: str = Field(min_length=1, max_length=80)
    service_kind: str = Field(min_length=1, max_length=80)
    comment: str = Field(default="", max_length=4000)
    container_ids: list[str] = Field(default_factory=list, max_length=50)


class CoordinationRequestUpdate(StrictModel):
    status: Literal["open", "in_progress", "resolved"]
    comment: str | None = Field(default=None, max_length=4000)
