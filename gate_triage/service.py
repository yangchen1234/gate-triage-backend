"""Atomic, single-process queue snapshots and replaceable scoring functions."""

from copy import deepcopy
from dataclasses import dataclass, replace
import importlib
import json
import logging
import math
from threading import RLock
from time import perf_counter
from typing import Any, Callable

from gate_triage.config import Settings
from gate_triage.models import DEFAULT_SCENARIO
from gate_triage.statistics import calculate_stats


logger = logging.getLogger(__name__)
ScoreFunction = Callable[[dict, dict], dict]
# The provider module owns its credentials, network timeout and API protocol.
# It must return {container_id: explanation}, never actions or scores.
ReasonFunction = Callable[[list[dict], dict], dict[str, str]]


def load_callable(reference: str) -> Callable:
    module, separator, name = reference.partition(":")
    if not separator or not module or not name:
        raise ValueError("Callable references must use module:function syntax")
    function = getattr(importlib.import_module(module), name)
    if not callable(function):
        raise ValueError(f"{reference} is not callable")
    return function


@dataclass(frozen=True)
class Snapshot:
    generation: int
    scenario: dict
    queue: list[dict]
    stats: dict
    scoring_ms: float
    llm: str = "template"
    llm_status: str = "disabled"


class QueueService:
    def __init__(self, settings: Settings, scorer: ScoreFunction | None = None,
                 reasoner: ReasonFunction | None = None):
        self.settings = settings
        self._scorer = scorer or load_callable(settings.scorer)
        self._reasoner = reasoner or (load_callable(settings.cloud_reasoner)
                                     if settings.cloud_reasoner else None)
        self._lock = RLock()
        self._raw = json.loads(settings.containers_file.read_text(encoding="utf-8"))
        self._validate_data()
        self._snapshot = self._build_snapshot(deepcopy(DEFAULT_SCENARIO), generation=1)

    def _validate_data(self) -> None:
        if not isinstance(self._raw, list):
            raise ValueError("containers.json must contain a JSON array")
        ids = set()
        for row in self._raw:
            if not isinstance(row, dict):
                raise ValueError("Each container must be a JSON object")
            identifier = row.get("container_id")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("Each container needs a non-empty container_id")
            if identifier in ids:
                raise ValueError(f"Duplicate container_id: {identifier}")
            ids.add(identifier)

    def _build_snapshot(self, scenario: dict, generation: int) -> Snapshot:
        started = perf_counter()
        scored = []
        for raw in self._raw:
            result = self._scorer(deepcopy(raw), deepcopy(scenario))
            if not isinstance(result, dict):
                raise ValueError("score(container, scenario) must return a dict")
            # A scorer may return computed fields only, or the entire container.
            # Never discard raw fields that it did not return.
            row = {**deepcopy(raw), **deepcopy(result)}
            if row.get("container_id") != raw["container_id"]:
                raise ValueError("The scorer must preserve container_id")
            for key in ("priority", "urgency", "conflict_score"):
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(f"{raw['container_id']}: {key} must be a finite number between 0 and 1")
            if not isinstance(row.get("reason"), str) or not row["reason"].strip():
                raise ValueError(f"{raw['container_id']}: reason must be non-empty")
            row["reason_source"] = "scorer"
            scored.append(row)
        # Pass original order to preserve input-order ties in both simulations.
        stats = calculate_stats(scored, scenario,
                                containers_per_lane_per_day=self.settings.containers_per_lane_per_day)
        queue = sorted(scored, key=lambda row: row["priority"], reverse=True)
        return Snapshot(generation, deepcopy(scenario), queue, stats,
                        round((perf_counter() - started) * 1000, 3),
                        llm_status="pending" if self._reasoner else "disabled")

    @property
    def has_reasoner(self) -> bool:
        return self._reasoner is not None

    def snapshot(self) -> Snapshot:
        # A reader receives its own copy, never the mutable cached objects.
        with self._lock:
            return deepcopy(self._snapshot)

    def update(self, changes: dict) -> Snapshot:
        with self._lock:
            current = self._snapshot
            updated = self._build_snapshot({**current.scenario, **changes}, current.generation + 1)
            # Failed scoring/statistics never replaces a working snapshot.
            self._snapshot = updated
            return deepcopy(updated)

    def enrich_reasons(self, generation: int) -> None:
        """Run cloud work outside the ranking path; ignore stale model results."""
        if not self._reasoner:
            return
        snapshot = self.snapshot()
        if snapshot.generation != generation:
            return
        selected = deepcopy(snapshot.queue[:self.settings.reason_limit])
        ids = {row["container_id"] for row in selected}
        try:
            reasons = self._reasoner(selected, deepcopy(snapshot.scenario))
            if not isinstance(reasons, dict) or set(reasons) != ids or any(
                not isinstance(value, str) or not value.strip() or len(value) > 2000
                for value in reasons.values()
            ):
                raise ValueError("Cloud reasoner must return one non-empty reason for every selected container_id")
            with self._lock:
                if self._snapshot.generation != generation:
                    return
                queue = deepcopy(self._snapshot.queue)
                for row in queue:
                    if row["container_id"] in reasons:
                        # Keep the rule explanation as evidence and constraint context.
                        row.setdefault("rule_reason", row["reason"])
                        row["reason"] = reasons[row["container_id"]]
                        row["reason_source"] = "cloud"
                self._snapshot = replace(self._snapshot, queue=queue, llm="cloud", llm_status="ready")
        except Exception:
            # Do not expose provider exception text, credentials or response bodies.
            logger.warning("Cloud explanations unavailable; keeping scoring reasons")
            with self._lock:
                if self._snapshot.generation == generation:
                    self._snapshot = replace(self._snapshot, llm="template", llm_status="fallback")
