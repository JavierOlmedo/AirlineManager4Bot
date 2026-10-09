"""Money bookkeeping shared by the bot and the GUI.

* Money samples -> estimated net income per day (used for the savings goal ETA).
* Market cache (aircraft list with prices) -> goal picker and goal price.

The bot owns the writes to ``data/state.json`` (inside ``Bot._state``); the GUI only
reads that file. ``data/market.json`` is written by the bot when it reads the market.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import paths
from i18n import t


def state_file() -> Path:
    """data/state.json of the active profile."""
    return paths.current().data / "state.json"


def market_file() -> Path:
    return paths.current().data / "market.json"

SAMPLE_EVERY = 300          # seconds between money samples
MAX_GAP = 1500              # a longer gap means the bot was stopped: no departures, no income
SAMPLE_WINDOW = 48 * 3600   # keep two days of samples
MIN_OBSERVED = 3600         # need one hour of running time before trusting the rate

# A money sample is [time, money, invested, spent, fuel, co2, fuel bought, co2 bought]: "invested" and "spent" are
# the bot's running totals of investments and of all its spending, "fuel" / "co2" what the tanks held (None until
# the market is read) and the last two the running totals the bot bought. Older samples only have the first three.
_SPENT, _FUEL, _CO2, _FUEL_BOUGHT, _CO2_BOUGHT = range(3, 8)


# ---------------------------------------------------------------------- income rate
def add_money_sample(state: dict, money: int, now: Optional[float] = None, fuel: Optional[int] = None,
                     co2: Optional[int] = None) -> bool:
    """Append a sample at most every SAMPLE_EVERY seconds. Returns True when stored."""
    now = time.time() if now is None else now
    samples = state.setdefault("money_samples", [])
    if samples and now - samples[-1][0] < SAMPLE_EVERY:
        return False
    bought = state.get("bought", {})
    samples.append([int(now), int(money), int(state.get("invested", 0)), int(state.get("spent_total", 0)),
                    fuel, co2, int(bought.get("fuel", 0)), int(bought.get("co2", 0))])
    cutoff = now - SAMPLE_WINDOW
    state["money_samples"] = [sample for sample in samples if sample[0] >= cutoff]
    return True


def _field(sample: list, index: int) -> Optional[int]:
    return sample[index] if len(sample) > index else None


def _per_day(state: dict, delta, min_seconds: int = MIN_OBSERVED) -> Optional[int]:
    """Sum of delta(sample, next sample) over the stretches the bot was running, per day. Stretches where delta
    returns None (data missing) are left out; None until *min_seconds* have been observed."""
    samples = state.get("money_samples", [])
    total = 0.0
    seconds = 0
    for s0, s1 in zip(samples, samples[1:]):
        gap = s1[0] - s0[0]
        if not 0 < gap <= MAX_GAP:
            continue
        value = delta(s0, s1)
        if value is not None:
            total += value
            seconds += gap
    if seconds < min_seconds:
        return None
    return int(total / seconds * 86400)


def income_per_day(state: dict, fuel_price: Optional[float] = None, co2_price: Optional[float] = None) -> Optional[int]:
    """Net cash generated per day while the bot runs (investments added back), None if unknown.

    Investments (aircraft, route fees, hangar slots) are added back because they are
    choices, not running costs. Fuel, CO2 and repairs stay in: they are the real cost of
    operating the fleet. With *fuel_price* / *co2_price* ($ per 1,000) fuel and CO2 count when
    they are burnt, not when they are bought: the change of what the tanks hold is valued at
    that price, so filling a tank does not look like a bad day.
    """
    def delta(s0: list, s1: list) -> Optional[float]:
        value = (s1[1] - s0[1]) + (s1[2] - s0[2])
        for index, price in ((_FUEL, fuel_price), (_CO2, co2_price)):
            if not price:
                continue
            before, after = _field(s0, index), _field(s1, index)
            if before is None or after is None:
                return None
            value += (after - before) * price / 1000
        return value
    return _per_day(state, delta)


def revenue_per_day(state: dict, min_seconds: int = MIN_OBSERVED) -> Optional[int]:
    """Gross income per day (tickets and rewards): the change of money plus everything the bot spent meanwhile."""
    def delta(s0: list, s1: list) -> Optional[float]:
        before, after = _field(s0, _SPENT), _field(s1, _SPENT)
        if before is None or after is None:
            return None
        return max(0, (s1[1] - s0[1]) + (after - before))  # a purchase made by hand is not lost revenue
    return _per_day(state, delta, min_seconds)


def usage_per_day(state: dict, kind: str) -> Optional[int]:
    """Fuel (lbs) or CO2 (quotas) burnt per day: what left the tank, counting what the bot bought meanwhile."""
    held, bought = (_FUEL, _FUEL_BOUGHT) if kind == "fuel" else (_CO2, _CO2_BOUGHT)

    def delta(s0: list, s1: list) -> Optional[float]:
        values = [_field(sample, index) for sample in (s0, s1) for index in (held, bought)]
        if None in values:
            return None
        before, bought_before, after, bought_after = values
        return max(0, before - after + bought_after - bought_before)
    return _per_day(state, delta)


def goal_progress(price: Optional[int], money: Optional[int], reserve: int, rate: Optional[int]) -> Optional[dict]:
    """Savings progress towards an aircraft of *price* keeping *reserve* untouched."""
    if not price or money is None:
        return None
    have = max(0, money - reserve)
    missing = max(0, price - have)
    eta_days = missing / rate if rate and rate > 0 else None
    return {
        "have": have,
        "missing": missing,
        "pct": min(100.0, have * 100 / price),
        "eta_days": eta_days,
        "reached": missing == 0,
    }


def fmt_days(days: Optional[float]) -> str:
    if days is None:
        return t("sin estimar")
    if days <= 0:
        return t("ya")
    hours = days * 24
    if hours < 1:
        return t("menos de 1 h")
    if hours < 48:
        return f"~{hours:.0f} h"
    return t("~{n} días", n=f"{days:.1f}")


def fmt_money(value: Optional[int]) -> str:
    """Compact money: $4.4M, $255k, $900."""
    if value is None:
        return "?"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}${value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{sign}${value / 1000:.0f}k"
    return f"{sign}${value:,}"


# ---------------------------------------------------------------------- growth ladder
AUTO_GOAL_NAMES = ("auto", "automático", "automatico", "automático (escalera)", "escalera",
                   "automatic", "automatic (ladder)", "ladder")
AUTO_GOAL_LABEL = "Automático (escalera)"


def is_auto_goal(name: str) -> bool:
    return (name or "").strip().lower() in AUTO_GOAL_NAMES


def pick_ladder(models: list[dict], income_day: Optional[int], budget_days: float, max_payback: float,
                fallback_budget: Optional[int] = None) -> Optional[dict]:
    """Next step of the growth ladder: the model that earns the most per day among those costing at most
    *budget_days* of income and paying for themselves within *max_payback* days.

    Each model dict needs "price" and "profit" (estimated net $/day). As income grows the budget grows,
    so the ladder climbs to bigger aircraft by itself.
    """
    budget = income_day * budget_days if income_day and income_day > 0 else fallback_budget
    if not budget:
        return None
    candidates = [m for m in models
                  if m.get("price") and m.get("profit", 0) > 0 and m["price"] <= budget
                  and m["price"] / m["profit"] <= max_payback]
    return max(candidates, key=lambda m: m["profit"]) if candidates else None


# ---------------------------------------------------------------------- files
def load_state(path: Optional[Path] = None) -> dict:
    try:
        state = json.loads(Path(path or state_file()).read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def save_market(models: list[dict], path: Optional[Path] = None) -> None:
    path = Path(path or market_file())
    try:
        paths.write_atomic(path, json.dumps({"updated": int(time.time()), "models": models}, indent=0))
    except OSError:
        pass


def load_market(path: Optional[Path] = None) -> list[dict]:
    try:
        data = json.loads(Path(path or market_file()).read_text(encoding="utf-8"))
        models = data.get("models", []) if isinstance(data, dict) else []
        return [m for m in models if isinstance(m, dict) and m.get("name")]
    except (OSError, ValueError):
        return []


def find_model(models: list[dict], name: str) -> Optional[dict]:
    """Exact (case-insensitive) match first, then substring."""
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    for model in models:
        if model["name"].lower() == wanted:
            return model
    for model in models:
        if wanted in model["name"].lower():
            return model
    return None
