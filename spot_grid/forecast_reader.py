"""Read-only adapter for crypto-signal-engine range_forecasts.

Requires optional psycopg 3: pip install 'psycopg[binary]'.
Pass a read-only database role; this module never issues writes.
"""
from datetime import timezone
from decimal import Decimal as D

from .planner import RangeForecast
from .quality import CoverageOutcome


def _aware(value):
    if value.tzinfo is None:
        raise ValueError("database timestamp lacks timezone")
    return value.astimezone(timezone.utc)


def decode_rows(rows):
    forecasts, outcomes = [], []
    for row in rows:
        symbol, generated, due, minutes, target, lower, upper, status, covered, evaluated = row
        forecasts.append(RangeForecast(
            symbol, _aware(generated), _aware(due), D(str(lower)),
            D(str(upper)), int(minutes), D(str(target))))
        if covered is not None and evaluated is not None:
            outcomes.append(CoverageOutcome(
                symbol, f"{minutes}m", _aware(evaluated), bool(covered),
                int(minutes)))
    return forecasts, outcomes


def load_forecasts(dsn, *, symbol, start, end):
    """Fetch forecasts and earlier evaluations needed for point-in-time coverage.

    Reads all rows for a symbol generated before end, including historical
    outcomes preceding start. Caller must filter decisions using evaluated_at.
    """
    if not symbol or start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("invalid symbol or date range")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("install psycopg[binary] to read PostgreSQL") from exc
    sql = """
        SELECT symbol, generated_at, due_at, horizon_minutes,
               target_coverage, lower_price, upper_price,
               status, covered, evaluated_at
        FROM range_forecasts
        WHERE symbol = %s AND generated_at < %s
        ORDER BY generated_at, horizon_minutes
    """
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on") as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (symbol, end))
            rows = cur.fetchall()
    forecasts, outcomes = decode_rows(rows)
    return [f for f in forecasts if start <= f.created_at < end], outcomes
