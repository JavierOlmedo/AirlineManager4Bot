"""One snapshot of everything the dashboards show, shared by the desktop window and the web page.

It is built from the bot's live stats plus the files the bot writes (data/state.json for the money
samples and price records, data/market.json for the aircraft list), so it also works while the bot is
stopped: it then shows the last known values.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from economy import find_model, fmt_days, fmt_money, goal_progress, income_per_day, is_auto_goal, pick_ladder
from i18n import language, t

if TYPE_CHECKING:
    from bot import Bot
    from config import AppConfig


def last_money(bot: "Bot", state: dict) -> Optional[int]:
    money = bot.stats().money
    if money is None:
        samples = state.get("money_samples") or []
        money = samples[-1][1] if samples else None
    return money


def ladder_step(cfg: "AppConfig", market: list[dict], income: Optional[int], money: Optional[int]) -> Optional[dict]:
    """The next aircraft of the growth ladder at this income (same rule as the bot)."""
    reserve = cfg.get_int("settings", "cash_reserve", 0)
    return pick_ladder(market, income, cfg.get_int("settings", "ladder_budget_days", 1),
                       cfg.get_int("settings", "ladder_max_payback", 5),
                       fallback_budget=max(0, (money or 0) - reserve))


def goal_status(cfg: "AppConfig", market: list[dict], money: Optional[int], income: Optional[int],
                goal_text: Optional[str] = None, live_price: Optional[int] = None) -> dict:
    """{name, price, progress} of the savings goal; *goal_text* overrides the saved goal (desktop preview)."""
    text = (cfg.get("settings", "goal_model") if goal_text is None else goal_text).strip()
    if is_auto_goal(text):
        model = ladder_step(cfg, market, income, money)
        name = t("Auto: {name}", name=model["name"]) if model else t("Automático")
        price = model.get("price") if model else None
    else:
        model = find_model(market, text)
        name = model["name"] if model else text
        price = model.get("price") if model else live_price
    progress = goal_progress(price, money, cfg.get_int("settings", "cash_reserve", 0), income)
    return {"name": name, "price": price, "progress": progress}


def _tank(holding: Optional[int], capacity: Optional[int], price: Optional[int], buy_at: Optional[int],
          record: Optional[list]) -> dict:
    pct = holding * 100 / capacity if holding is not None and capacity else None
    return {"holding": holding, "capacity": capacity, "pct": pct, "price": price, "buy_at": buy_at,
            "record": record[0] if record else None, "record_at": record[1] if record else None}


def snapshot(bot: "Bot", cfg: "AppConfig", state: dict, market: list[dict], restart_in: Optional[int] = None) -> dict:
    stats = bot.stats()
    now = time.time()
    money = last_money(bot, state)
    income = stats.income_day if stats.income_day is not None else income_per_day(state)
    records = state.get("price_records", {})
    goal = goal_status(cfg, market, money, income, live_price=stats.goal_price)
    progress = goal["progress"]
    campaign_left = int(stats.campaign_ends - now) if stats.campaign_ends and stats.campaign_ends > now else None
    next_at = bot.next_cycle_at  # read once: the bot thread clears it when a cycle starts
    next_in = int(next_at - now) if next_at else None
    return {
        "lang": language(),
        "state": t(bot.state.value),
        "state_key": bot.state.name,
        "alive": bot.is_alive(),
        "error": bot.last_error,
        "next_cycle_in": max(0, next_in) if next_in is not None else None,
        "restart_in": restart_in,
        "dry_run": bot.dry_run,
        "mode": t(stats.mode) if stats.mode else None,
        "updated_at": stats.updated_at,
        "money": money,
        "income_day": income,
        "points": stats.points,
        "reputation": stats.reputation,
        "campaign_left": campaign_left,
        "fuel": _tank(stats.fuel, stats.fuel_capacity, stats.fuel_price, stats.fuel_buy_at, records.get("fuel")),
        "co2": _tank(stats.co2, stats.co2_capacity, stats.co2_price, stats.co2_buy_at, records.get("co2")),
        "fleet": {"size": stats.fleet_size, "inflight": stats.inflight, "parked": stats.parked, "pending": stats.pending,
                  "hangar_free": stats.hangar_free, "hangar_capacity": stats.hangar_capacity},
        "goal": {
            "name": goal["name"],
            "price": goal["price"],
            "price_text": fmt_money(goal["price"]) if goal["price"] else None,
            "pct": progress["pct"] if progress else None,
            "missing": progress["missing"] if progress else None,
            "eta_text": fmt_days(progress["eta_days"]) if progress else None,
            "reached": bool(progress and progress["reached"]),
        },
    }


def fmt_clock(seconds: Optional[int]) -> str:
    """3725 -> '1:02 h', 125 -> '02:05'."""
    if seconds is None:
        return ""
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d} h"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
