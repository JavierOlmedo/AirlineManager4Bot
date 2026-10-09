"""Seat layout by route demand: business (J) and first (F) seats wherever the route has that demand.

Every route has its own daily demand per class, and the aircraft flew all-economy: economy ran out while
business and first demand went unused (B737 on EPRZ: Y 32 of 560 left, J 281 of 281 and F 84 of 84 untouched).
A J seat takes 2 economy slots and an F seat 3, and the autoprices are Y = 0.4 x km + 170, J = 0.8 x km + 560,
F = 1.2 x km + 1,200 in easy mode (0.3 / 0.6 / 0.9 x km + 150 / 500 / 1,000 in realism, see gamemode.py), so in
both modes first pays the most per slot, then business, then economy. The best layout therefore fills first
class up to its daily demand, then business, and leaves the rest economy.

Screen facts (verified 2026-10-05):
* Routes list (routes_main.php): one [id^='routeMainList'] row per aircraft with a route; its link calls
  fleet_details.php?id=<aircraft id> and ".col-10 .s-text" holds the airports ("LEMD - EPRZ").
* fleet_details.php?id=<id> -> #detailsAction: "#seat-layout .col-4" = Y / J / F seats; "#list-demand .col-4"
  = remaining / daily demand per class; the Auto button calls ticketPriceSuggest(y, j, f, ...) with the route
  autoprices; #eTicket / #bTicket / #fTicket hold the current ticket prices.
* maint_plan_do.php?type=modify&id=<id> -> #maintPlanAction: the Modify button calls modifyAction(id, this),
  which sends the page globals eSeat / bSeat / fSeat (seat counts) and mod1..3; the max of #seatSlider2 is the
  number of economy slots. Each changed J seat costs $8,000 and F seat $16,000, and the work takes 60 s per Y,
  90 s per J and 220 s per F seat changed. Only possible at a base (or inbound to it), else an .alert-danger.
"""
from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from selenium.webdriver.common.by import By

from economy import find_model, fmt_money, load_market
from fleet import CO2_PER_PAX_KM, ENGINE_FUEL, TURNAROUND_H
from gamemode import EASY, GameMode
from helpers import clean_response, fmt, to_int
from maintenance import read_fleet
from notify import esc

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.asientos")

SLOTS = (1, 2, 3)              # economy slots taken by a Y, J and F seat
SEAT_COST = (0, 8000, 16000)   # $ per changed Y, J and F seat
SEAT_SECONDS = (60, 90, 220)   # work time per changed Y, J and F seat
RECHECK_SECONDS = 12 * 3600    # look at each aircraft at most twice a day
MAX_DETAILS = 8                # aircraft examined per cycle
MAX_CHANGES = 2                # modifications per cycle
MIN_GAIN_PCT = 5               # ignore changes that add less than this to the aircraft's revenue
MAX_PANELS = 4                 # modify panels opened per cycle
# Checklist task "Fly with your first 1st class passenger" (its cell is #claim_7 in welcome.php): $100,000 once,
# so while it is open the first aircraft that gets first-class seats earns that on top of its tickets.
FIRST_CLASS_TASK = "claim_7"
FIRST_CLASS_REWARD = 100_000

# Performance modifications of the same panel (#mod1..3, costs in the page globals mod1cost..mod3cost, each
# takes 800 s in the workshop and is permanent). The page script tests "$('#modN').is(':checked') && X==0":
# X is 1 when the aircraft already has that modification.
MODS = {1: "CO2 -10 %", 2: "velocidad +10 %", 3: "fuel -10 %"}
MOD_SECONDS = 800
_MOD_INSTALLED_RE = re.compile(r"#mod(\d)'\)\.is\(':checked'\)\s*&&\s*(\d+)\s*==\s*0")

_ROUTES_JS = """
return Array.from(document.querySelectorAll("#popContent [id^='routeMainList']")).map(row => {
  const link = row.querySelector("a[onclick*='fleet_details.php']");
  const id = ((link ? link.getAttribute("onclick") : "").match(/fleet_details\\.php\\?id=(\\d+)/) || [])[1];
  const route = row.querySelector(".col-10 .s-text");
  return {id: id || null, name: link ? link.textContent.trim() : "", route: route ? route.textContent.trim() : ""};
});
"""

_DETAILS_JS = """
const root = document.getElementById("detailsAction");
if (!root) { return null; }
const nums = el => ((el ? el.textContent : "").match(/[\\d,]+/g) || []).map(n => Number(n.replace(/,/g, "")));
const seats = Array.from(root.querySelectorAll("#seat-layout .col-4")).map(c => nums(c)[0] || 0);
const demand = Array.from(root.querySelectorAll("#list-demand .col-4")).map(c => { const n = nums(c); return n.length > 1 ? n[1] : (n[0] || 0); });
const auto = root.querySelector("[onclick*='ticketPriceSuggest']");
const args = auto ? ((auto.getAttribute("onclick").match(/ticketPriceSuggest\\(([^)]*)\\)/) || [])[1] || "") : "";
const tickets = ["eTicket", "bTicket", "fTicket"].map(i => { const e = root.querySelector("#" + i); return e ? Number(e.value) || 0 : 0; });
return {seats: seats, demand: demand, auto: args.split(",").slice(0, 3).map(Number), tickets: tickets};
"""


@dataclass(frozen=True)
class Layout:
    y: int
    j: int
    f: int

    @property
    def seats(self) -> tuple[int, int, int]:
        return self.y, self.j, self.f

    @property
    def slots(self) -> int:
        return sum(n * s for n, s in zip(self.seats, SLOTS))

    def __str__(self) -> str:
        return f"Y{self.y} J{self.j} F{self.f}"


@dataclass
class SeatPlan:
    aircraft_id: str
    reg: str
    model: str
    route: str
    old: Layout
    new: Layout
    demand: tuple[float, float, float]   # this aircraft's share of the daily demand per class
    prices: tuple[float, float, float]
    per_seat: float                      # passengers one seat carries per day
    revenue: float                       # current revenue per day
    gain: float                          # extra revenue per day with the new layout
    cost: int
    hours: float
    distance: float = 0.0                # route length (km)
    legs: float = 0.0                    # one-way flights a day
    fuel_km: float = 0.0                 # listed fuel use of the model (lbs/km)
    bonus: float = 0.0                   # one-off money the new layout brings (checklist reward)

    @property
    def payback(self) -> float:
        """Days to earn back the work: its price plus the revenue lost while the aircraft is in the workshop,
        minus any one-off reward."""
        lost = self.revenue / 24 * self.hours
        return max(0.0, self.cost + lost - self.bonus) / self.gain if self.gain > 0 else float("inf")


def mod_gains(plan: SeatPlan, layout: Layout, fuel_price: float, co2_price: float) -> dict[int, float]:
    """Extra profit per day of each performance modification with this layout: CO2 and fuel save 10 % of their
    daily cost; speed adds 10 % more flights (more tickets, as far as the route demand allows, and more fuel)."""
    def day(per_seat: float) -> tuple[float, float]:
        sold = [min(n * per_seat, wanted) for n, wanted in zip(layout.seats, plan.demand)]
        revenue = sum(price * pax for price, pax in zip(plan.prices, sold))
        return revenue, sum(pax * slots for pax, slots in zip(sold, SLOTS))

    revenue, slot_pax = day(plan.per_seat)
    co2_per_slot_pax = CO2_PER_PAX_KM * plan.distance * co2_price / 1000
    fuel = plan.legs * plan.fuel_km * ENGINE_FUEL * plan.distance * fuel_price / 1000
    fast_revenue, fast_slot_pax = day(plan.per_seat * 1.1)
    speed = (fast_revenue - revenue) - 0.1 * fuel - (fast_slot_pax - slot_pax) * co2_per_slot_pax
    return {1: 0.1 * slot_pax * co2_per_slot_pax, 2: speed, 3: 0.1 * fuel}


def choose_mods(gains: dict[int, float], costs: dict[int, float], installed: set[int], revenue: float,
                max_payback: float) -> list[int]:
    """Modifications not installed yet that pay back (price + workshop time) within *max_payback* days."""
    lost = revenue / 24 * MOD_SECONDS / 3600
    return [mod for mod in MODS if mod not in installed and costs.get(mod, 0) > 0 and gains.get(mod, 0) > 0
            and (costs[mod] + lost) / gains[mod] <= max_payback]


# ---------------------------------------------------------------------- economics (pure functions)
def best_layout(slots: int, demand: tuple[float, float, float], per_seat: float) -> Layout:
    """First class up to its daily demand, then business, the rest economy (per slot F pays more than J, J more than Y)."""
    if per_seat <= 0 or slots <= 0:
        return Layout(max(slots, 0), 0, 0)
    first = min(slots // SLOTS[2], int(demand[2] / per_seat))
    business = min((slots - first * SLOTS[2]) // SLOTS[1], int(demand[1] / per_seat))
    return Layout(slots - first * SLOTS[2] - business * SLOTS[1], business, first)


def daily_revenue(layout: Layout, demand: tuple[float, float, float], prices: tuple[float, float, float],
                  per_seat: float) -> float:
    """Ticket revenue per day: each class sells seats x passengers per seat, capped by its daily demand."""
    return sum(price * min(seats * per_seat, wanted) for seats, wanted, price in zip(layout.seats, demand, prices))


def change_cost(old: Layout, new: Layout) -> tuple[int, float]:
    """($, hours) of a seat modification, as the game's modify panel computes them."""
    diffs = [abs(a - b) for a, b in zip(old.seats, new.seats)]
    cost = sum(d * c for d, c in zip(diffs, SEAT_COST))
    seconds = sum(d * s for d, s in zip(diffs, SEAT_SECONDS))
    return cost, seconds / 3600


def legs_per_day(distance: float, speed: float, mode: GameMode = EASY) -> float:
    """One-way flights a day when the aircraft flies back to back (same model as fleet.daily_profit)."""
    return 24 / (max(distance, 300) / (max(speed, 100) * mode.speed) + TURNAROUND_H)


def planning_load(bot: "Bot") -> float:
    """Expected occupancy: the current reputation (it includes running campaigns), else the measured load."""
    reputation = bot.stats().reputation
    return reputation / 100 if reputation and 10 <= reputation <= 100 else bot.load_factor()


def evaluate(aircraft_id: str, name: str, route: str, info: dict, share: int, load: float,
             market: list[dict], mode: GameMode = EASY) -> Optional[SeatPlan]:
    """Best layout for one aircraft from its fleet details; None when the details are incomplete."""
    seats, demand, auto, tickets = info.get("seats") or [], info.get("demand") or [], info.get("auto") or [], info.get("tickets") or []
    if len(seats) != 3 or len(demand) != 3 or len(tickets) != 3:
        return None
    auto = (list(auto) + [0, 0, 0])[:3]
    prices = tuple(float(t or a or 0) for t, a in zip(tickets, auto))
    base_price = auto[0] or tickets[0]
    if not base_price or prices[0] <= 0:
        return None
    reg, _, model = name.partition(" - ")
    distance = mode.distance(base_price, auto[1] or tickets[1])  # from the autoprice formula of the game mode
    known = find_model(market, model.strip() or reg)
    legs = legs_per_day(distance, (known or {}).get("speed") or 700, mode)
    per_seat = load * legs
    share_demand = tuple(d / max(share, 1) for d in demand)
    old = Layout(*seats)
    new = best_layout(old.slots, share_demand, per_seat)
    revenue = daily_revenue(old, share_demand, prices, per_seat)
    gain = daily_revenue(new, share_demand, prices, per_seat) - revenue
    cost, hours = change_cost(old, new)
    return SeatPlan(aircraft_id, reg.strip() or aircraft_id, model.strip(), route, old, new, share_demand, prices,
                    per_seat, revenue, gain, cost, hours, distance, legs, float((known or {}).get("fuel") or 0))


def worth_it(plan: SeatPlan, max_payback: float) -> bool:
    return (plan.new != plan.old and plan.gain >= max(1000.0, plan.revenue * MIN_GAIN_PCT / 100)
            and plan.payback <= max_payback)


def _airports(route: str) -> tuple[str, ...]:
    return tuple(sorted(part.strip() for part in route.split("-") if part.strip()))


# ---------------------------------------------------------------------- bot step
def optimize_seats(bot: "Bot") -> None:
    """Workshop step: look at the aircraft waiting at the base and modify those that would earn clearly more,
    with a better seat layout (auto_seats) and/or the speed, fuel and CO2 modifications (auto_mods)."""
    now = time.time()
    do_seats = bot.config.get_bool("options", "auto_seats", True)
    do_mods = bot.config.get_bool("options", "auto_mods", True)
    checked: dict = dict(bot.recall("seat_checks", {}))
    installed: dict = dict(bot.recall("mods_installed", {}))
    fleet = bot.recent_fleet()
    if fleet is None:
        bot.open_popup("maintenance_main.php", "Maintenance", "nav_maintenance")
        fleet = read_fleet(bot)
        bot.close_popup()
    due = [a for a in fleet if a.at_base and now - float(checked.get(a.id, 0)) >= RECHECK_SECONDS][:MAX_DETAILS]
    if not due:
        log.debug("Taller: ningún avión en la base pendiente de revisar.")
        return

    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    rows = {row["id"]: row for row in bot.js(_ROUTES_JS) or [] if row.get("id")}
    per_route = Counter(_airports(row["route"]) for row in rows.values())
    load = planning_load(bot)
    market = load_market()
    max_payback = max(0.5, float(bot.config.get_int("settings", "seats_max_payback", 3)))
    reward = FIRST_CLASS_REWARD if FIRST_CLASS_TASK in bot.recall("checklist", {}).get("open_ids", []) else 0
    seat_plans: list[SeatPlan] = []
    mod_plans: list[SeatPlan] = []
    for aircraft in due:
        if bot.stopping:
            break
        row = rows.get(aircraft.id)
        if row is None:
            continue  # no route yet: it is looked at once it has one
        bot.ajax(f"fleet_details.php?id={aircraft.id}", "detailsAction")
        plan = evaluate(aircraft.id, row["name"], row["route"], bot.js(_DETAILS_JS) or {},
                        per_route[_airports(row["route"])], load, market, bot.mode)
        checked[aircraft.id] = now
        if plan is None:
            log.debug("%s: no he podido leer los asientos o la demanda de su ruta.", aircraft.reg)
            continue
        if reward and plan.old.f == 0 and plan.new.f > 0:
            plan.bonus = reward
            if do_seats and worth_it(plan, max_payback):
                reward = 0  # paid once: only one aircraft counts on it
            else:
                plan.bonus = 0
        log.debug("%s (%s, %s): %s -> %s, +%s/día, coste %s, %.1f h, se paga en %.1f días.", plan.reg, plan.model,
                  plan.route, plan.old, plan.new, fmt_money(int(plan.gain)), fmt_money(plan.cost), plan.hours, plan.payback)
        if do_seats and worth_it(plan, max_payback):
            seat_plans.append(plan)
        elif do_mods and set(installed.get(aircraft.id, [])) != set(MODS):
            mod_plans.append(plan)
        else:
            continue
        checked.pop(aircraft.id, None)  # only marked once the workshop panel has been looked at
    bot.close_popup()
    # A simulation must not keep the real bot from looking at these aircraft for the next 12 hours.
    if not bot.dry_run:
        bot.remember("seat_checks", {key: value for key, value in checked.items() if now - float(value) < 7 * 86400})

    plans = sorted(seat_plans, key=lambda p: p.payback) + mod_plans
    if not plans:
        log.info("Taller: revisados %d aviones en la base (ocupación prevista %.0f %%), ninguno gana bastante con "
                 "otros asientos ni con mejoras.", len(due), load * 100)
        return
    # Plans over this cycle's limit, or that fail (money, no longer at the base), stay unmarked: next time.
    bot.open_popup("maintenance_main.php", "Maintenance", "nav_maintenance")
    changes = 0
    for plan in plans[:MAX_PANELS]:
        if bot.stopping or changes >= MAX_CHANGES:
            break
        outcome = apply_plan(bot, plan, max_payback, do_seats, do_mods)
        if outcome is None:
            continue  # try again next cycle
        changes += outcome
        if not bot.dry_run:
            checked[plan.aircraft_id] = time.time()
            bot.remember("seat_checks", checked)
    bot.close_popup()


def _mod_panel(bot: "Bot", html: str) -> tuple[dict[int, float], set[int]]:
    """(price of each modification, modifications already installed) from the modify panel."""
    costs = bot.js("return [window.mod1cost, window.mod2cost, window.mod3cost];") or []
    prices = {mod: float(cost) for mod, cost in zip(MODS, costs) if isinstance(cost, (int, float))}
    installed = {int(mod) for mod, flag in _MOD_INSTALLED_RE.findall(html or "") if flag != "0"}
    return prices, installed


def apply_plan(bot: "Bot", plan: SeatPlan, max_payback: float, do_seats: bool = True, do_mods: bool = False) -> Optional[int]:
    """Open the modify panel of one aircraft and make the changes that pay. Returns the number of changes made
    (0 = looked at, nothing worth doing) or None when the panel is not available now (retry next cycle)."""
    # The modify panel lives inside the Plan tab, and a finished modification replaces that tab: reload it each time.
    bot.ajax("maint_plan.php", "maintAction")
    panel = bot.ajax(f"maint_plan_do.php?type=modify&id={plan.aircraft_id}", "maintPlanAction")
    buttons = panel.find_elements(By.XPATH, ".//button[contains(@onclick, 'modifyAction')]")
    if not buttons:
        log.info("%s: ahora no se puede modificar (no está en la base o ya está en el taller).", plan.reg)
        return None
    seats_change = False
    if do_seats and plan.new != plan.old:
        # The slider knows the real number of economy slots; recompute if the current layout leaves some unused.
        slots = to_int(str(bot.js("try { return $('#seatSlider2').slider('option', 'max'); } catch (e) { return null; }")))
        if slots and slots != plan.old.slots:
            plan.new = best_layout(slots, plan.demand, plan.per_seat)
            plan.gain = daily_revenue(plan.new, plan.demand, plan.prices, plan.per_seat) - plan.revenue
            plan.cost, plan.hours = change_cost(plan.old, plan.new)
            if plan.new.f == 0:
                plan.bonus = 0
        seats_change = worth_it(plan, max_payback)
    layout = plan.new if seats_change else plan.old
    revenue = plan.revenue + (plan.gain if seats_change else 0)

    chosen: list[int] = []
    mods_cost = 0.0
    mods_gain = 0.0
    if do_mods:
        prices, installed = _mod_panel(bot, panel.get_attribute("innerHTML"))
        known = dict(bot.recall("mods_installed", {}))
        if not bot.dry_run:
            known[plan.aircraft_id] = sorted(installed)
            bot.remember("mods_installed", known)
        gains = mod_gains(plan, layout, bot.fuel_cost_basis(), bot.co2_cost_basis())
        chosen = choose_mods(gains, prices, installed, revenue, max_payback)
        mods_cost = sum(prices[mod] for mod in chosen)
        mods_gain = sum(gains[mod] for mod in chosen)
        log.debug("%s: mejoras %s, ya instaladas %s, ganancia/día %s.", plan.reg,
                  {MODS[m]: round(prices.get(m, 0)) for m in MODS}, sorted(installed),
                  {MODS[m]: round(gains[m]) for m in MODS})
    if not seats_change and not chosen:
        log.debug("%s: nada que cambiar en el taller.", plan.reg)
        return 0

    cost = (plan.cost if seats_change else 0) + int(round(mods_cost))
    hours = (plan.hours if seats_change else 0) + len(chosen) * MOD_SECONDS / 3600
    gain = (plan.gain if seats_change else 0) + mods_gain
    bonus = plan.bonus if seats_change else 0
    parts = []
    if seats_change:
        parts.append(f"asientos {plan.old} -> {plan.new}")
        if bonus:
            parts.append(f"cobra ${fmt(int(bonus))} del checklist (primer pasajero de primera clase)")
    if chosen:
        parts.append("mejoras " + ", ".join(MODS[mod] for mod in chosen))
    payback = max(0.0, cost + revenue / 24 * hours - bonus) / gain if gain > 0 else float("inf")
    detail = (f"{plan.reg} ({plan.model}, {plan.route}): {'; '.join(parts)}, +{fmt_money(int(gain))}/día estimado, "
              f"coste ${fmt(cost)}, {hours:.1f} h en el taller, se paga en {payback:.1f} días")
    if not bot.can_spend(cost, f"el taller de {plan.reg}"):
        return None
    if bot.dry_run:
        log.info("[SIMULACIÓN] Haría en el taller: %s.", detail)
        bot.notify(f"🧪 SIMULACIÓN: haría en el taller {esc(detail)}.", silent=True)
        return 1
    # Same request the game's own Modify button sends after moving the seat slider and ticking the modifications.
    bot.js("window.eSeat = arguments[0]; window.bSeat = arguments[1]; window.fSeat = arguments[2];"
           "window.mod1 = arguments[3]; window.mod2 = arguments[4]; window.mod3 = arguments[5];",
           *layout.seats, *(1 if mod in chosen else 0 for mod in MODS))
    before = bot.read_money()
    bot.click_element(buttons[0])
    response = bot.wait_text("//*[@id='maintPlanActionDo']", timeout=15)
    if not bot.confirm_purchase(before, cost, f"el taller de {plan.reg}", "maintPlanActionDo"):
        return None
    bot.spent(cost, invest=True)
    if seats_change:
        bot.count("seats")
        bot.count("seats_spent", plan.cost)
    if chosen:
        bot.count("mods", len(chosen))
        bot.count("mods_spent", int(round(mods_cost)))
        known = dict(bot.recall("mods_installed", {}))
        known[plan.aircraft_id] = sorted(set(known.get(plan.aircraft_id, [])) | set(chosen))
        bot.remember("mods_installed", known)
    log.info("Taller: %s. %s", detail, clean_response(response))
    icon = "💺" if seats_change else "🛠️"
    bot.notify(f"{icon} <b>Taller</b>: {esc(detail)}.\n{esc(clean_response(response, 200))}".rstrip())
    return 1
