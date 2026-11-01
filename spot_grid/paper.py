"""Deterministic paper-trading session, no live exchange integration."""
from dataclasses import replace
from .engine import GridEngine


class PaperSession:
    def __init__(self, config, *, fill_model=None):
        self.engine = GridEngine(replace(config, fill_model=fill_model) if fill_model is not None else config)
        self.events = []

    def on_candle(self, candle):
        before = len(self.engine.fills)
        self.engine.on_candle(candle, path="low_first",
                              allow_same_candle_reentry=False)
        equity = self.engine.usdt + self.engine.asset * self.engine.last_price
        self.events.append({
            "time": candle.get("time"),
            "fills": list(self.engine.fills[before:]),
            "stopped": self.engine.stopped,
            "equity": str(equity),
        })
        return self.events[-1]

    def report(self):
        return {"snapshot": self.engine.snapshot(),
                "events": list(self.events)}
