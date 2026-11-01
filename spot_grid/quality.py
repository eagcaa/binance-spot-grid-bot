"""Point-in-time forecast coverage: never count outcomes not yet evaluated."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal as D


@dataclass(frozen=True)
class CoverageOutcome:
    symbol: str
    horizon: str
    evaluated_at: datetime
    covered: bool
    horizon_minutes: int | None = None


@dataclass(frozen=True)
class CoverageResult:
    eligible: bool
    samples: int
    coverage: D | None
    reason: str | None


def coverage_at(outcomes, *, symbol, horizon=None, horizon_minutes=None, as_of, target=D("0.80"),
                min_samples=30, min_span=timedelta(0)):
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if not D(0) <= target <= D(1) or min_samples < 1:
        raise ValueError("invalid coverage policy")
    if horizon_minutes is not None and horizon_minutes <= 0:
        raise ValueError("invalid horizon_minutes")
    known = []
    for outcome in outcomes:
        if outcome.evaluated_at.tzinfo is None:
            raise ValueError("outcome evaluated_at must be timezone-aware")
        same_horizon = (outcome.horizon_minutes == horizon_minutes
                        if horizon_minutes is not None and outcome.horizon_minutes is not None
                        else horizon is not None and outcome.horizon == horizon)
        if (outcome.symbol == symbol and same_horizon
                and outcome.evaluated_at < as_of):
            known.append(outcome)
    count = len(known)
    if min_span < timedelta(0):
        raise ValueError("min_span must be nonnegative")
    if count >= min_samples and min_span > timedelta(0):
        span = max(o.evaluated_at for o in known) - min(o.evaluated_at for o in known)
        if span < min_span:
            rate = D(sum(bool(o.covered) for o in known)) / D(count)
            return CoverageResult(False, count, rate, "insufficient_time_span")
    rate = D(sum(bool(o.covered) for o in known)) / D(count) if count else None
    if count < min_samples:
        return CoverageResult(False, count, rate, "insufficient_history")
    if rate < target:
        return CoverageResult(False, count, rate, "coverage_below_target")
    return CoverageResult(True, count, rate, None)
