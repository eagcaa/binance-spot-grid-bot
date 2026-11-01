"""Deterministic paper-trading session, no live exchange integration."""
from dataclasses import replace
from .engine import GridEngine


class PaperSession:
    def __init__(self, config):
        self.engine = GridEngine(replace(config, fill_model='through'))
        self.events = []

    def on_candle(self, candle):
        before = len(self.engine.fills)
        self.engine.on_candle(candle, path="low_first",
                              allow_same_candle_reentry=False)
        self.events.append({
            "time": candle.get("time"),
            "fills": list(self.engine.fills[before:]),
            "stopped": self.engine.stopped,
            "equity": self.engine.snapshot()["equity"],
        })
        return self.engine.snapshot()

    def report(self):
        return {"snapshot": self.engine.snapshot(),
                "events": list(self.events)}
