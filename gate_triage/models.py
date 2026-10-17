"""Only the scenario is constrained here; Ryan's container fields are preserved."""

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


DEFAULT_SCENARIO = {"lanes_open": 8, "customs_online": True, "power_zone_b": True}


class ScenarioPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lanes_open: StrictInt | None = Field(default=None, ge=0, le=8)
    customs_online: StrictBool | None = None
    power_zone_b: StrictBool | None = None

    @field_validator("lanes_open", "customs_online", "power_zone_b", mode="before")
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError("Omit an unchanged field instead of sending null")
        return value
