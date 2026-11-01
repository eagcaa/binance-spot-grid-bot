import io
import json
from decimal import Decimal as D

import pytest

from spot_grid import exchange_rules


def test_reads_symbol_specific_filters(monkeypatch):
    payload = {"symbols": [{
        "symbol": "DOGEUSDT", "status": "TRADING",
        "isSpotTradingAllowed": True,
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": "0.00001000"},
            {"filterType": "LOT_SIZE", "stepSize": "1.00000000"},
            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
        ],
    }]}
    seen = []

    def fake_urlopen(url, timeout):
        seen.append(url)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(exchange_rules, "urlopen", fake_urlopen)
    assert exchange_rules.read_symbol_rules("DOGEUSDT") == {
        "tick": D("0.00001000"),
        "qty_step": D("1.00000000"),
        "min_notional": D("5.00000000"),
    }
    assert "symbol=DOGEUSDT" in seen[0]
    assert "/api/v3/exchangeInfo?" in seen[0]


def test_fails_closed_on_missing_filters(monkeypatch):
    payload = {"symbols": [{"symbol": "PYTHUSDT", "status": "TRADING",
                            "filters": [{"filterType": "PRICE_FILTER", "tickSize": "0.0001"}]}]}
    monkeypatch.setattr(exchange_rules, "urlopen",
                        lambda url, timeout: io.BytesIO(json.dumps(payload).encode()))
    with pytest.raises(ValueError, match="incomplete"):
        exchange_rules.read_symbol_rules("PYTHUSDT")


def test_fails_closed_on_non_trading_symbol(monkeypatch):
    payload = {"symbols": [{"symbol": "DOGEUSDT", "status": "BREAK",
                            "filters": []}]}
    monkeypatch.setattr(exchange_rules, "urlopen",
                        lambda url, timeout: io.BytesIO(json.dumps(payload).encode()))
    with pytest.raises(ValueError, match="not available"):
        exchange_rules.read_symbol_rules("DOGEUSDT")
