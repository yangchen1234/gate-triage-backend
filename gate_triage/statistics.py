"""Transparent FIFO-versus-priority demurrage simulation for the demo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from math import isfinite
from typing import Any


_ACTIONS = ("release", "slow", "inspect", "reroute")


@dataclass(frozen=True)
class _Entry:
    arrived_at: datetime
    priority: Decimal
    demurrage: Decimal


def _number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{field} must be a finite number")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite number")
    return number


def _arrival(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO 8601 date or datetime")
    try:
        iso_value = value.strip()
        if iso_value.endswith("Z"):
            iso_value = iso_value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(iso_value)
        # Date-only values and naive datetimes deliberately mean UTC. Nothing
        # in this calculation depends on the machine's clock or time zone.
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be an ISO 8601 date or datetime") from exc


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    result = float(value)
    if not isfinite(result):
        raise ValueError("demurrage total is too large for a finite JSON number")
    return result


def calculate_stats(
    containers: Sequence[Mapping[str, Any]],
    scenario: Mapping[str, Any],
    *,
    containers_per_lane_per_day: int = 12,
) -> dict[str, Any]:
    """Compare the cost of unserved containers under two queue orderings.

    Daily capacity is ``lanes_open * containers_per_lane_per_day``. Every action
    participates in this queue-capacity simulation; action does not grant an
    actual release authorization. FIFO uses ``arrived_at`` ascending and the
    optimized queue uses ``priority`` descending. Ties preserve input order.

    ``demurrage_usd_per_day`` is the supplied daily accrual, summed directly for
    unserved containers. ``free_days_left`` is metadata, not an extra discount.
    ISO date-only and naive datetime arrivals are interpreted as UTC. Invalid
    input raises ValueError without mutating the containers or scenario.
    """
    lanes_open = scenario.get("lanes_open")
    if isinstance(lanes_open, bool) or not isinstance(lanes_open, int) or lanes_open < 0:
        raise ValueError("scenario.lanes_open must be a non-negative integer")
    if (
        isinstance(containers_per_lane_per_day, bool)
        or not isinstance(containers_per_lane_per_day, int)
        or containers_per_lane_per_day <= 0
    ):
        raise ValueError("containers_per_lane_per_day must be a positive integer")

    counts = dict.fromkeys(_ACTIONS, 0)
    entries: list[_Entry] = []
    for index, container in enumerate(containers):
        prefix = f"containers[{index}]"
        if not isinstance(container, Mapping):
            raise ValueError(f"{prefix} must be an object")
        action = container.get("action")
        if not isinstance(action, str) or action not in counts:
            raise ValueError(f"{prefix}.action must be one of {', '.join(_ACTIONS)}")
        priority = _number(container.get("priority"), f"{prefix}.priority")
        if not Decimal(0) <= priority <= Decimal(1):
            raise ValueError(f"{prefix}.priority must be between 0 and 1")
        demurrage = _number(
            container.get("demurrage_usd_per_day"),
            f"{prefix}.demurrage_usd_per_day",
        )
        if demurrage < 0:
            raise ValueError(f"{prefix}.demurrage_usd_per_day must be non-negative")
        arrived_at = _arrival(container.get("arrived_at"), f"{prefix}.arrived_at")
        entries.append(_Entry(arrived_at, priority, demurrage))
        counts[action] += 1

    capacity = lanes_open * containers_per_lane_per_day
    fifo = sorted(entries, key=lambda entry: entry.arrived_at)
    optimized = sorted(entries, key=lambda entry: entry.priority, reverse=True)

    # Allocate enough Decimal precision for exact addition of the supplied
    # values, including fractional cents, before converting at the JSON edge.
    integer_digits = max((entry.demurrage.adjusted() + 1 for entry in entries), default=1)
    fractional_digits = max(
        (max(0, -entry.demurrage.as_tuple().exponent) for entry in entries),
        default=0,
    )
    with localcontext() as context:
        context.prec = max(
            28,
            max(1, integer_digits) + fractional_digits + len(str(len(entries))) + 1,
        )
        baseline = sum((entry.demurrage for entry in fifo[capacity:]), Decimal(0))
        optimized_cost = sum((entry.demurrage for entry in optimized[capacity:]), Decimal(0))
        savings = baseline - optimized_cost

    return {
        **counts,
        "baseline_demurrage_usd_per_day": _json_number(baseline),
        "optimized_demurrage_usd_per_day": _json_number(optimized_cost),
        "savings_usd_per_day": _json_number(savings),
        "scenario": deepcopy(dict(scenario)),
    }
