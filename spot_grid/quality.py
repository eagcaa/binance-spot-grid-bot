"""Point-in-time forecast coverage: never count outcomes not yet evaluated."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal as D


@dataclass(frozen=True)
class CoverageOutcome:
    symbol: str
    horizon: str
    evaluated_at: datetime
    covered: bool


@dataclass(frozen=True)
class CoverageResult:
    eligible: bool
    samples: int
    coverage: D | None
    reason: str | None


def coverage_at(outcomes, *, symbol, horizon, as_of, target=D("0.80"),
                min_samples=30):
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if not D(0) <= target <= D(1) or min_samples < 1:
        raise ValueError("invalid coverage policy")
    known = []
    for outcome in outcomes:
        if outcome.evaluated_at.tzinfo is None:
            raise ValueError("outcome evaluated_at must be timezone-aware")
        if (outcome.symbol == symbol and outcome.horizon == horizon
                and outcome.evaluated_at < as_of):
            known.append(outcome)
    count = len(known)
    rate = D(sum(bool(o.covered) for o in known)) / D(count) if count else None
    if count < min_samples:
        return CoverageResult(False, count, rate, "insufficient_history")
    if rate < target:
        return CoverageResult(False, count, rate, "coverage_below_target")
    return CoverageResult(True, count, rate, None)
