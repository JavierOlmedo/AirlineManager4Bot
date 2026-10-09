"""Fleet automation: routes for parked aircraft and buying the best-value aircraft.

Screen facts (verified 2026-09-30):
* Routes popup (`routes_main.php`): `#hParked` / `#hPending` counters;
  `fleet_parked.php` -> #routesContainer lists `#routeMainParkedList<id>` blocks.
* Research tab (`research_main.php` -> #routeAction): `#hubSelect` holds the hub id;
  `research_main.php?mode=search&rwy=..&dist=..&depId=..&arr=0&arrId=0&charter=0`
  -> #resResult with `.sorter` rows (data-distance / data-yclass / data-jclass /
  data-fclass / data-rwy, onclick contains `arr=<airportId>`).
* `route_research_route.php?dep=..&arr=..` -> #rDetails with `#capAc` (capable
  aircraft, option value "id;lat;lon;speed;range;arr") and "A/C on route".
* `new_route_info.php?id=<ac>&airportId=<arr>&mode=res` -> #newRouteInfo panel:
  `#introAuto` (autoprice), `#routeReg`, `#btnCreateNewRoute`, "Route fee".
* Order tab (`ac_orders.php?first=true` -> #routeAction): `#acListItems .acListItem`
  rows with data-range / data-speed / data-capacity / data-fuel / data-price and
  the model id in the onclick; `ac_orders.php?mode=detail&id=..&charter=0` ->
  #acModel with `#acReg`, `#hubSelection`, `#btnPurchaseIntro`, `#accountLow`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from selenium.webdriver.common.by import By

from economy import (find_model, fmt_days, fmt_money, goal_progress, is_auto_goal, load_market, pick_ladder,
                     save_market)
from gamemode import EASY, GameMode
from helpers import clean_response, fmt, to_int
from notify import esc

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.rutas")
log_fleet = logging.getLogger("am4bot.flota")
log_market = logging.getLogger("am4bot.aviones")

MAX_ROUTE_TRIES = 8  # busiest candidate routes checked per parked aircraft
BIG_SEATS = 150      # from this capacity an aircraft is "big": long routes, goal candidate
GOAL_SAFETY = 2      # a small aircraft must pay back in less than half the time left to the goal

# Everything below reads the game by structure (ids, classes, data attributes, onclick handlers),
# never by visible text, so the bot works with the game in English, Spanish or any other language.

# Route fee: the only bold red figure of the new-route panel.
_ROUTE_FEE_JS = """
const figures = document.querySelectorAll("#newRouteInfo .text-danger.font-weight-bold");
return figures.length ? figures[figures.length - 1].textContent : null;
"""
# "A/C on route": first row of the small table under the demand table in the route details.
_ON_ROUTE_JS = """
const cell = document.querySelector("#rDetails table.m-text:not(.table-bordered) tr td.text-right");
return cell ? cell.textContent : null;
"""

_PARKED_JS = """
return Array.from(document.querySelectorAll("#routesContainer [id^='routeMainParkedList']")).map(el => {
  const bolds = Array.from(el.querySelectorAll("b")).map(b => b.textContent.trim());
  const header = el.querySelector(".col-6.text-right");                 // "90 Seats" / "90 Asientos"
  const seats = ((header ? header.textContent : "").match(/[\\d,]+/) || [])[0];
  return {id: el.id.replace("routeMainParkedList", ""), model: bolds[0] || "?", reg: bolds[1] || "", seats: seats || ""};
});
"""

_CANDIDATES_JS = """
return Array.from(document.querySelectorAll("#resResult #list .sorter")).map(el => {
  const arr = ((el.getAttribute("onclick") || "").match(/arr=(\\d+)/) || [])[1];
  const title = el.querySelector(".exo");
  return {arr: arr || null, name: title ? title.textContent.trim() : "?", distance: el.dataset.distance || "0",
          y: el.dataset.yclass || "0", j: el.dataset.jclass || "0", f: el.dataset.fclass || "0", rwy: el.dataset.rwy || "0"};
});
"""

_MODELS_JS = """
return Array.from(document.querySelectorAll("#acListItems .acListItem"))
  .filter(el => el.offsetParent !== null)
  .map(el => {
    const id = ((el.getAttribute("onclick") || "").match(/id=(\\d+)/) || [])[1];
    const name = el.querySelector("b");
    return {id: id || null, name: name ? name.textContent.trim() : "?", range: el.dataset.range || "0",
            speed: el.dataset.speed || "0", capacity: el.dataset.capacity || "0", fuel: el.dataset.fuel || "0",
            price: el.dataset.price || "0"};
  });
"""


@dataclass
class ParkedAircraft:
    id: str
    model: str
    reg: str
    seats: int


@dataclass
class RouteCandidate:
    arr_id: str
    name: str
    distance: float
    y: int
    j: int
    f: int
    runway: int


@dataclass
class AircraftModel:
    id: str
    name: str
    range_km: int
    speed: int
    capacity: int
    fuel: int
    price: int
    score: float = field(default=0.0)    # estimated net profit per day / price
    profit: float = field(default=0.0)   # estimated net profit per day ($)


# Economics calibrated on the airline's own flight history (01/10/2026, easy mode): the economy autoprice
# is 0.4 $/km + 170 and a leg takes distance / (1.5 x cruise speed) - both depend on the game mode, see
# gamemode.py -, the engine burns ~94 % of the listed fuel, CO2 is ~0.18 kg per passenger-km, and the bot
# leaves an aircraft ~6 minutes on the ground.
# The load factor is measured by the bot every cycle (it follows the airline reputation).
LOAD_DEFAULT = 0.55
TURNAROUND_H = 0.1
ENGINE_FUEL = 0.94
CO2_PER_PAX_KM = 0.18
ROUTE_DEMAND_Y = 1200   # economy passengers per day on a busy route: caps what one aircraft can sell


def daily_profit(model: AircraftModel, distance: int, load: float, fuel_price: float, co2_price: float,
                 mode: GameMode = EASY) -> float:
    """Estimated net profit per day of one aircraft flying *distance* km legs back to back
    (flight speed and economy autoprice of the game mode)."""
    if distance < 300 or model.price <= 0 or model.speed <= 0:
        return 0.0
    legs = 24 / (distance / (model.speed * mode.speed) + TURNAROUND_H)
    passengers = min(model.capacity * load * legs, ROUTE_DEMAND_Y)
    income = passengers * mode.fare(0, distance)
    fuel = legs * model.fuel * ENGINE_FUEL * distance * fuel_price / 1000
    co2 = passengers * CO2_PER_PAX_KM * distance * co2_price / 1000
    return income - fuel - co2


# ---------------------------------------------------------------------- entry point
_ONBOARD_JS = """
return Array.from(document.querySelectorAll("#popContent [id^='routeMainList']"))
  .filter(row => row.querySelector("[id^='routesTimer']"))          // in flight: the row shows who is on board
  .map(row => {
    const link = row.querySelector("a");                              // "EC-003-2 - DC-9-10"
    const info = link ? link.parentElement.querySelector(".s-text") : null;   // "Onboard: 49 / 0 / 0" (Y / J / F)
    const nums = (((info || {}).textContent || "").match(/\\d+/g) || []).map(Number);
    // in economy slots: a business passenger takes 2, a first-class passenger 3
    return {name: link ? link.textContent.trim() : "", onboard: (nums[0] || 0) + 2 * (nums[1] || 0) + 3 * (nums[2] || 0)};
  });
"""


def measure_load(bot: "Bot") -> None:
    """Median load factor of the aircraft in flight (occupied economy slots / slots), smoothed over cycles."""
    market = load_market()
    loads = []
    for row in bot.js(_ONBOARD_JS) or []:
        model_name = row["name"].split(" - ", 1)[-1].strip()
        model = find_model(market, model_name)
        if model and model.get("capacity") and row["onboard"]:
            loads.append(min(1.0, row["onboard"] / model["capacity"]))
    if len(loads) >= 3:
        loads.sort()
        bot.record_load(loads[len(loads) // 2])


def manage_fleet(bot: "Bot") -> None:
    cfg = bot.config
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    measure_load(bot)
    parked = to_int(bot.js("return $('#hParked').text();")) or 0
    pending = to_int(bot.js("return $('#hPending').text();")) or 0
    bot.update_stats(parked=parked, pending=pending)
    log_fleet.info("%d aviones aparcados sin ruta, %d pendientes de entrega.", parked, pending)

    budget = max(1, cfg.get_int("settings", "fleet_actions_per_cycle", 2))
    if cfg.get_bool("options", "auto_route") and parked > 0:
        created = create_routes(bot, budget)
        budget -= created
        parked -= created
    if cfg.get_bool("options", "autobuy_aircraft") and budget > 0:
        if parked > 0:
            log_market.info("No compro aviones mientras haya %d aparcados sin ruta.", parked)
        else:
            buy_aircraft(bot)
    bot.close_popup()


# ---------------------------------------------------------------------- routes
def read_parked(bot: "Bot") -> list[ParkedAircraft]:
    bot.ajax("fleet_parked.php", "routesContainer")
    parked = []
    for row in bot.js(_PARKED_JS) or []:
        if row.get("id"):
            parked.append(ParkedAircraft(row["id"], row["model"], row["reg"] or row["id"], to_int(row["seats"]) or 0))
    return parked


def search_routes(bot: "Bot", hub_id: str, max_distance: int, min_runway: int) -> list[RouteCandidate]:
    bot.ajax(
        f"research_main.php?mode=search&rwy={min_runway}&dist={max_distance}&depId={hub_id}&arr=0&arrId=0&charter=0",
        "resResult",
    )
    candidates = []
    for row in bot.js(_CANDIDATES_JS) or []:
        if not row.get("arr"):
            continue
        try:
            distance = float(row["distance"])
        except ValueError:
            distance = 0.0
        candidates.append(RouteCandidate(
            row["arr"], row["name"], distance,
            to_int(row["y"]) or 0, to_int(row["j"]) or 0, to_int(row["f"]) or 0, to_int(row["rwy"]) or 0,
        ))
    return candidates


def _daily_seats_sold(aircraft: ParkedAircraft, model: Optional[dict], distance: float, load: float,
                      mode: GameMode = EASY) -> float:
    """Economy passengers per day one aircraft would carry on a route of *distance* km (80 % of it, as margin)."""
    speed = (model or {}).get("speed") or 700
    legs = 24 / (max(distance, 300) / (speed * mode.speed) + TURNAROUND_H)
    return aircraft.seats * load * legs * 0.8


def _route_demand(candidate: RouteCandidate, premium: bool) -> int:
    """Daily demand in economy slots. With the seat layout by demand, business and first count too (2 and 3 slots)."""
    return candidate.y + 2 * candidate.j + 3 * candidate.f if premium else candidate.y


def create_routes(bot: "Bot", max_routes: int) -> int:
    cfg = bot.config
    parked = read_parked(bot)
    if not parked:
        log.info("No hay aviones aparcados en la lista de flota.")
        return 0
    max_distance = cfg.get_int("settings", "route_max_distance", 2000)
    max_distance_big = cfg.get_int("settings", "route_max_distance_big", 6000)
    min_runway = cfg.get_int("settings", "route_min_runway", 5000)
    market = load_market()
    premium = cfg.get_bool("options", "auto_seats")
    created = 0
    used: set[str] = set()

    for aircraft in parked:
        if created >= max_routes or bot.stopping:
            break
        # Big aircraft (150+ seats) earn most on long routes; never search beyond what the model can fly.
        limit = max_distance_big if aircraft.seats >= BIG_SEATS else max_distance
        known = find_model(market, aircraft.model)
        if known and known.get("range"):
            limit = min(limit, int(known["range"]))
        # Creating a route closes the popup, so start from a fresh Routes > Research screen every time.
        bot.open_popup("routes_main.php", "Routes", "nav_routes")
        bot.ajax("research_main.php", "routeAction")
        hub_id = bot.js("return $('#hubSelect').val() || (typeof depId !== 'undefined' ? String(depId) : null);")
        if not hub_id:
            log.warning("No encuentro el hub de salida en la pantalla de búsqueda de rutas.")
            break
        outcome = "none"
        # If nothing suitable comes up (range, runway), retry with shorter searches.
        for distance in (limit, limit // 2, limit // 4):
            if distance < 500 or bot.stopping:
                break
            candidates = [c for c in search_routes(bot, hub_id, distance, min_runway) if c.arr_id not in used]
            candidates.sort(key=lambda c: _route_demand(c, premium), reverse=True)
            # Prefer routes with enough daily demand to fill this aircraft at the measured occupancy
            # (a B737 put on a 560 pax/day route ran out of passengers by mid-day).
            enough = [c for c in candidates
                      if _route_demand(c, premium) >= _daily_seats_sold(aircraft, known, c.distance, bot.load_factor(), bot.mode)]
            if enough and len(enough) < len(candidates):
                log.debug("%d de %d rutas tienen demanda para llenar el %s.", len(enough), len(candidates), aircraft.model)
            tries = (enough or candidates)[:MAX_ROUTE_TRIES]
            if not tries:
                log.info("Sin rutas candidatas a menos de %d km (pista >= %d ft).", distance, min_runway)
                continue
            log.info("%s (%s, %d asientos): reviso las %d rutas con más demanda hasta %d km ...",
                     aircraft.reg, aircraft.model, aircraft.seats, len(tries), distance)
            capable_found = False
            for candidate in tries:
                if bot.stopping:
                    break
                details = bot.ajax(f"route_research_route.php?dep={hub_id}&arr={candidate.arr_id}", "rDetails")
                capable = details.find_elements(By.XPATH, f".//*[@id='capAc']/option[starts-with(@value, '{aircraft.id};')]")
                if not capable:
                    log.debug("%s no puede volar %s (alcance o pista).", aircraft.reg, candidate.name)
                    continue
                capable_found = True
                on_route = to_int(bot.js(_ON_ROUTE_JS)) or 0
                if on_route:
                    log.debug("%s ya tiene %d aviones.", candidate.name, on_route)
                    continue
                outcome = create_route(bot, aircraft, candidate)
                break
            if outcome != "none" or capable_found:
                break
        if outcome in ("created", "dry"):
            created += 1
            used.add(candidate.arr_id)
        elif outcome == "stop":
            break
        else:
            log.info("%s: ninguna ruta válida (alcance, pista o ya cubierta).", aircraft.reg)
    return created


def create_route(bot: "Bot", aircraft: ParkedAircraft, candidate: RouteCandidate) -> str:
    """Returns 'created', 'dry' (dry run) or 'stop' (money or page problem)."""
    bot.js("if (typeof hideFlightInfo === 'function') { hideFlightInfo(); } arrId = arguments[0];", int(candidate.arr_id))
    panel = bot.ajax(f"new_route_info.php?id={aircraft.id}&airportId={candidate.arr_id}&mode=res", "newRouteInfo")
    fee = to_int(bot.js(_ROUTE_FEE_JS))
    if not bot.can_spend(fee, f"la ruta {candidate.name}", essential=True):  # an aircraft without a route earns nothing
        bot.js("$('#newRouteInfo').hide();")
        return "stop"

    autoprice = panel.find_elements(By.XPATH, ".//*[@id='introAuto']")
    if autoprice:
        bot.click_element(autoprice[0])
        bot.pause(0.8, 1.2)
    prices = bot.js(
        "return ['eSeat', 'bSeat', 'fSeat'].map(i => { const e = document.getElementById(i); return e ? e.value : ''; });"
    ) or ["", "", ""]
    if not prices[0]:
        log.warning("El autoprecio no ha rellenado los billetes de %s, no creo la ruta.", candidate.name)
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    reg = bot.js("return $('#routeReg').val();") or ""
    summary = (
        f"{candidate.name} ({candidate.distance:,.0f} km, demanda Y {candidate.y} / J {candidate.j} / F {candidate.f}) "
        f"para {aircraft.reg} ({aircraft.model}), billetes ${prices[0]} / ${prices[1]} / ${prices[2]}, "
        f"matrícula {reg}, tasa de ruta ${fmt(fee)}"
    )
    if bot.dry_run:
        log.info("[SIMULACIÓN] Crearía la ruta %s.", summary)
        bot.notify(f"🧪 SIMULACIÓN: crearía la ruta {esc(summary)}.", silent=True)
        bot.js("$('#newRouteInfo').hide();")
        return "dry"

    before = bot.read_money()
    bot.click_element(panel.find_element(By.XPATH, ".//*[@id='btnCreateNewRoute']"))
    response = bot.wait_text("//*[@id='routeNewAction']", timeout=15)
    if not bot.confirm_purchase(before, fee, f"la ruta {candidate.name}", "routeNewAction"):
        bot.js("$('#newRouteInfo').hide();")
        return "stop"
    bot.spent(fee, invest=True)
    bot.count("routes")
    log.info("Ruta creada: %s. %s", summary, clean_response(response))
    bot.notify(f"🛫 <b>Ruta creada</b>: {esc(summary)}.\n{esc(clean_response(response, 200))}".rstrip())
    bot.js("$('#newRouteInfo').hide();")
    return "created"


# ---------------------------------------------------------------------- aircraft market
def read_models(bot: "Bot") -> list[AircraftModel]:
    models = []
    for row in bot.js(_MODELS_JS) or []:
        if not row.get("id"):
            continue
        models.append(AircraftModel(
            row["id"], row["name"], to_int(row["range"]) or 0, to_int(row["speed"]) or 0,
            to_int(row["capacity"]) or 0, to_int(row["fuel"]) or 0, to_int(row["price"]) or 0,
        ))
    return models


def score_models(bot: "Bot", models: list[AircraftModel]) -> None:
    """Estimate daily profit and return for every model, on the routes it will actually fly."""
    cfg = bot.config
    fuel_price = bot.fuel_cost_basis()
    co2_price = bot.co2_cost_basis()
    load = bot.load_factor()
    short = cfg.get_int("settings", "route_max_distance", 2000)
    long = cfg.get_int("settings", "route_max_distance_big", 6000)
    for model in models:
        distance = min(model.range_km, long if model.capacity >= BIG_SEATS else short)
        model.profit = daily_profit(model, distance, load, fuel_price, co2_price, bot.mode)
        model.score = model.profit / model.price if model.price > 0 else 0.0


def payback_days(model: AircraftModel) -> float:
    return 1 / model.score if model.score > 0 else float("inf")


def buy_aircraft(bot: "Bot") -> None:
    cfg = bot.config
    bot.open_popup("routes_main.php", "Routes", "nav_routes")
    bot.ajax("ac_orders.php?first=true", "routeAction")
    models = read_models(bot)
    if not models:  # the list sometimes renders a moment after the Ajax call returns
        bot.pause(1.5, 2.0)
        models = read_models(bot)
    if not models:
        log_market.warning("La lista del mercado de aviones está vacía.")
        return
    score_models(bot, models)
    save_market([{"id": m.id, "name": m.name, "price": m.price, "capacity": m.capacity, "range": m.range_km,
                  "speed": m.speed, "fuel": m.fuel, "score": round(m.score, 4), "profit": int(m.profit)}
                 for m in models])

    stats = bot.stats()
    if stats.money is None:
        log_market.warning("Saldo desconocido, no compro aviones.")
        return
    reserve = cfg.get_int("settings", "cash_reserve", 0)
    budget = stats.money - reserve
    max_price = cfg.get_int("settings", "aircraft_max_price", 0)
    hangar_free = stats.hangar_free

    goal_name = cfg.get("settings", "goal_model") if cfg.get_bool("options", "save_for_goal") else ""
    if goal_name:
        save_for_goal(bot, models, goal_name, budget, reserve, max_price, hangar_free)
        return

    if hangar_free is not None and hangar_free < 1:
        log_market.info("Hangar lleno: no hay hueco para otro avión.")
        return
    preferred = cfg.get("settings", "aircraft_model")
    if preferred:
        wanted = [m for m in models if m.name.lower() == preferred.lower()] or \
                 [m for m in models if preferred.lower() in m.name.lower()]
        if not wanted:
            log_market.warning("No encuentro el modelo '%s' en el mercado.", preferred)
            return
        choice = wanted[0]
        if choice.price > budget:
            log_market.info("%s cuesta $%s, más de los $%s disponibles tras la reserva de caja.", choice.name, fmt(choice.price), fmt(budget))
            return
    else:
        affordable = [m for m in models if 0 < m.price <= budget and (max_price == 0 or m.price <= max_price) and m.score > 0]
        if not affordable:
            log_market.info("Ningún avión asequible con $%s tras la reserva de caja.", fmt(budget))
            return
        affordable.sort(key=lambda m: m.score, reverse=True)
        choice = affordable[0]
        log_market.info("Aviones más rentables: %s", ", ".join(f"{m.name} ({m.score * 100:.0f}%/día, ${fmt(m.price)})" for m in affordable[:3]))
    order_aircraft(bot, choice)


def save_for_goal(bot: "Bot", models: list[AircraftModel], goal_name: str, budget: int, reserve: int,
                  max_price: int, hangar_free: Optional[int]) -> None:
    """Savings mode: buy the goal aircraft as soon as it fits, and meanwhile only aircraft that
    pay for themselves well before the goal would be reached (they make the goal come sooner).
    With the automatic goal the target is the next step of the growth ladder."""
    stats = bot.stats()
    if is_auto_goal(goal_name):
        cfg = bot.config
        pick = pick_ladder([{"name": m.name, "price": m.price, "profit": m.profit} for m in models
                            if max_price == 0 or m.price <= max_price],
                           stats.income_day, cfg.get_int("settings", "ladder_budget_days", 1),
                           cfg.get_int("settings", "ladder_max_payback", 5), fallback_budget=max(budget, 0))
        goal = next((m for m in models if pick and m.name == pick["name"]), None)
        if goal is None:
            log_market.info("Escalera: ningún avión cumple el presupuesto y la amortización ahora mismo.")
            return
        log_market.info("Escalera: siguiente avión %s (%s, %d plazas, gana ~%s/día, se paga en ~%.1f días).",
                        goal.name, fmt_money(goal.price), goal.capacity, fmt_money(int(goal.profit)), payback_days(goal))
    else:
        goal = next((m for m in models if m.name.lower() == goal_name.lower()), None) or \
            next((m for m in models if goal_name.lower() in m.name.lower()), None)
    if goal is None:
        log_market.warning("No encuentro el avión objetivo '%s' en el mercado: no compro nada hasta corregirlo.", goal_name)
        return
    bot.update_stats(goal_price=goal.price)
    progress = goal_progress(goal.price, stats.money, reserve, stats.income_day)
    if progress is None:  # no price for the goal in the market list, or the balance is unknown
        log_market.info("Objetivo %s: sin precio o sin saldo conocido, no compro nada en este ciclo.", goal.name)
        return
    status = (f"Objetivo {goal.name}: {fmt_money(progress['have'])} de {fmt_money(goal.price)} ({progress['pct']:.0f}%), "
              f"faltan {fmt_money(progress['missing'])}, llegada {fmt_days(progress['eta_days'])}")

    if progress["reached"]:
        if hangar_free is not None and hangar_free < 1:
            log_market.info("%s. Hay dinero pero no hueco en el hangar; se ampliará en el próximo ciclo.", status)
            return
        log_market.info("🎯 ¡Objetivo alcanzado! %s", status)
        order_aircraft(bot, goal, goal=True)
        return

    if not bot.config.get_bool("options", "goal_invest"):
        log_market.info("%s. Solo ahorro.", status)
        return
    eta = progress["eta_days"]
    if eta is None:
        log_market.info("%s. Aún no conozco el ritmo de ingresos: solo ahorro.", status)
        return
    if hangar_free is not None and hangar_free < 2:
        log_market.info("%s. Guardo el último hueco del hangar para el objetivo.", status)
        return
    candidates = [m for m in models
                  if m.name != goal.name and 0 < m.price <= budget and (max_price == 0 or m.price <= max_price)
                  and payback_days(m) * GOAL_SAFETY < eta]
    if not candidates:
        log_market.info("%s. Ningún otro avión asequible se amortiza antes, así que ahorro.", status)
        return
    candidates.sort(key=lambda m: m.score, reverse=True)
    choice = candidates[0]
    log_market.info("%s. Compro un %s porque se amortiza en ~%.1f días y adelanta el objetivo.",
                    status, choice.name, payback_days(choice))
    order_aircraft(bot, choice)


def order_aircraft(bot: "Bot", choice: AircraftModel, goal: bool = False) -> bool:
    detail = bot.ajax(f"ac_orders.php?mode=detail&id={choice.id}&charter=0", "acModel")
    low = detail.find_elements(By.XPATH, ".//*[@id='accountLow']")
    if low and low[0].is_displayed():
        log_market.info("El juego dice que el saldo no llega para un %s.", choice.name)
        return False
    reg = bot.js("return $('#acReg').val();") or ""
    summary = f"1 x {choice.name} por ${fmt(choice.price)} (matrícula {reg}, {choice.capacity} pax, {fmt(choice.range_km)} km de alcance)"
    if bot.dry_run:
        log_market.info("[SIMULACIÓN] Pediría %s.", summary)
        bot.notify(f"🧪 SIMULACIÓN: pediría {esc(summary)}.", silent=True)
        return True
    before = bot.read_money()
    bot.click_element(detail.find_element(By.XPATH, ".//*[@id='btnPurchaseIntro']"))
    response = bot.wait_text("//*[@id='orderAction']", timeout=15)
    if not bot.confirm_purchase(before, choice.price, f"el pedido de {choice.name}", "orderAction"):
        return False
    bot.spent(choice.price, invest=True)
    bot.count("aircraft")
    free = bot.stats().hangar_free
    if free is not None:
        bot.update_stats(hangar_free=max(0, free - 1))
    log_market.info("Pedido: %s. %s", summary, clean_response(response))
    title = "🎯 <b>¡Objetivo conseguido! Avión pedido</b>" if goal else "🛒 <b>Avión pedido</b>"
    bot.notify(f"{title}: {esc(summary)}.\n{esc(clean_response(response, 200))}".rstrip())
    return True
