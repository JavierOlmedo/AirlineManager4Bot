"""Fuel / CO2 price history and the smart-buy rule.

Prices change every 30 minutes. The market popup embeds the last 10 prices in a
chart call (``fuel_startFuelChart([..])`` / ``co2_startCo2Chart([..])``), so every
visit adds up to 5 hours of history even if the bot was off. The history is kept
in ``data/prices.json`` keyed by 30-minute window.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import paths

WINDOW_SECONDS = 1800
MIN_SAMPLES = 12  # half a day of prices before the percentile rule is trusted

_CHART_RE = {
    "fuel": re.compile(r"fuel_startFuelChart\(\s*\[([\d,\s]*)\]"),
    "co2": re.compile(r"co2_startCo2Chart\(\s*\[([\d,\s]*)\]"),
}


def chart_prices(html: str, kind: str) -> list[int]:
    """The price series embedded in the market popup, oldest first (last item = current window)."""
    match = _CHART_RE[kind].search(html or "")
    if not match:
        return []
    return [int(item) for item in match.group(1).split(",") if item.strip().isdigit()]


def history_file() -> Path:
    """data/prices.json of the active profile."""
    return paths.current().data / "prices.json"


def percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    index = round(max(0.0, min(100.0, pct)) / 100 * (len(ordered) - 1))
    return ordered[index]


class PriceHistory:
    def __init__(self, path: Optional[Path] = None, keep_days: int = 14):
        self.path = Path(path or history_file())
        self.keep_days = keep_days
        self._data: dict[str, dict[str, int]] = {"fuel": {}, "co2": {}}
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for kind in self._data:
            entries = raw.get(kind, {}) if isinstance(raw, dict) else {}
            self._data[kind] = {str(key): int(value) for key, value in entries.items() if str(key).isdigit()}

    def save(self) -> None:
        cutoff = int((time.time() - self.keep_days * 86400) // WINDOW_SECONDS)
        for kind in self._data:
            self._data[kind] = {key: value for key, value in self._data[kind].items() if int(key) >= cutoff}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=0, sort_keys=True), encoding="utf-8")
        except OSError:
            pass

    # ------------------------------------------------------------------ updates
    def add(self, kind: str, price: int, at: Optional[float] = None) -> None:
        key = str(int((at if at is not None else time.time()) // WINDOW_SECONDS))
        self._data[kind][key] = int(price)

    def add_series(self, kind: str, prices: list[int], last_window_start: float) -> None:
        """Store a chart series whose last value belongs to the window starting at *last_window_start*."""
        for offset, price in enumerate(reversed(prices)):
            self.add(kind, price, last_window_start - offset * WINDOW_SECONDS)

    # ------------------------------------------------------------------ queries
    def series(self, kind: str, days: Optional[float] = None) -> list[tuple[int, int]]:
        """[(window start timestamp, price)] oldest first; all of it when *days* is None."""
        cutoff = -1 if days is None else int((time.time() - days * 86400) // WINDOW_SECONDS)
        return sorted((int(key) * WINDOW_SECONDS, price) for key, price in self._data[kind].items() if int(key) >= cutoff)

    def recent(self, kind: str, days: float) -> list[int]:
        cutoff = int((time.time() - days * 86400) // WINDOW_SECONDS)
        return [price for key, price in self._data[kind].items() if int(key) >= cutoff]

    def summary(self, kind: str, days: float, pct: float) -> Optional[dict]:
        prices = self.recent(kind, days)
        if len(prices) < MIN_SAMPLES:
            return None
        return {
            "samples": len(prices),
            "min": min(prices),
            "max": max(prices),
            "median": percentile(prices, 50),
            "threshold": percentile(prices, pct),
        }
