"""Autorepair and A-checks through the game's Maintenance > Plan screen.

Screen facts (verified 2026-09-30): the Plan tab lists one `.maint-list-sort`
row per aircraft with data-reg / data-type / data-wear / data-hours / data-base
and a `#controls<id>` block. `maint_plan_do.php?type=repair|check&id=<id>` loads
a panel into #maintPlanAction with the cost and a "Plan repair" / "Plan check"
button; the button is missing when nothing can be done (fully repaired, not at
a base). Everything is located by ids, classes and onclick handlers, never by the
visible text, so it works with the game in any language.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from selenium.webdriver.common.by import By

from helpers import clean_response, fmt, to_int
from notify import esc

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.mant")

# Language-independent hooks: the "Plan repair / Plan check" buttons are the only ones calling
# maint_plan_do.php?mode=do, and the total cost is the only bold red figure of the section.
_PLAN_BUTTON = ".//button[contains(@onclick, 'mode=do')]"
_TOTAL_COST = ".text-danger.font-weight-bold"


def section_cost(section) -> Optional[int]:
    figures = section.find_elements(By.CSS_SELECTOR, _TOTAL_COST)
    return to_int(figures[-1].get_attribute("textContent")) if figures else None

_ROWS_JS = """
return Array.from(document.querySelectorAll("#maintAction .maint-list-sort")).map(row => {
  const controls = row.querySelector("[id^='controls']");
  return {
    id: controls ? controls.id.replace("controls", "") : null,
    reg: row.dataset.reg || "", model: row.dataset.type || "",
    wear: row.dataset.wear || "0", hours: row.dataset.hours || "0", base: row.dataset.base || "0"
  };
});
"""


@dataclass
class Aircraft:
    id: str
    reg: str
    model: str
    wear: float
    hours_to_check: int
    at_base: bool


def read_fleet(bot: "Bot") -> list[Aircraft]:
    bot.ajax("maint_plan.php", "maintAction")
    fleet: list[Aircraft] = []
    for row in bot.js(_ROWS_JS) or []:
        if not row.get("id"):
            continue
        try:
            wear = float(row["wear"])
        except ValueError:
            wear = 0.0
        try:
            hours = int(float(row["hours"]))
        except ValueError:
            hours = 0
        fleet.append(Aircraft(row["id"], row["reg"].upper(), row["model"], wear, hours, row["base"] == "1"))
    bot.cache_fleet(fleet)
    return fleet


def run_maintenance(bot: "Bot") -> None:
    cfg = bot.config
    bot.open_popup("maintenance_main.php", "Maintenance", "nav_maintenance")
    fleet = read_fleet(bot)
    bot.update_stats(fleet_size=len(fleet))
    if not fleet:
        log.info("Mantenimiento: no hay aviones.")
        bot.close_popup()
        return

    worst = max(fleet, key=lambda a: a.wear)
    soonest = min(fleet, key=lambda a: a.hours_to_check)
    log.info(
        "Flota: %d aviones | mayor desgaste %.1f%% (%s) | próximo A-check en %d h (%s)",
        len(fleet), worst.wear, worst.reg, soonest.hours_to_check, soonest.reg,
    )

    repair_at = cfg.get_int("settings", "repair_wear_pct", 40)
    check_at = cfg.get_int("settings", "check_hours_min", 20)
    do_repair = cfg.get_bool("options", "auto_repair")
    do_check = cfg.get_bool("options", "auto_check")

    for aircraft in sorted(fleet, key=lambda a: -a.wear):
        if bot.stopping:
            break
        if do_repair and aircraft.wear >= repair_at:
            plan(bot, aircraft, "repair")
        if do_check and aircraft.hours_to_check <= check_at:
            plan(bot, aircraft, "check")
    if not bot.stopping:
        check_hangar(bot)
    bot.close_popup()


# Hangars tab (hangars.php -> #maintAction): ".xl-text span" = max PAX aircraft, the last cell of the
# second table row = available slots; upgrade buttons call hangars.php?mode=upgrade&amount=1|10.
_HANGAR_JS = """
const root = document.getElementById("maintAction");
if (!root) { return null; }
const cap = root.querySelector(".xl-text span");
const rows = root.querySelectorAll("table tr");
const cell = rows.length > 1 ? rows[1].querySelector("td:last-child") : null;  // first td is the icon
return {capacity: cap ? cap.textContent : "", free: cell ? cell.textContent : ""};
"""


def check_hangar(bot: "Bot") -> None:
    """Read the free hangar slots and buy one more when they run low (option auto_hangar)."""
    panel = bot.ajax("hangars.php", "maintAction")
    data = bot.js(_HANGAR_JS) or {}
    capacity, free = to_int(data.get("capacity")), to_int(data.get("free"))
    if free is None:
        log.debug("No he podido leer los huecos del hangar.")
        return
    bot.update_stats(hangar_free=free, hangar_capacity=capacity)
    keep_free = max(1, bot.config.get_int("settings", "hangar_min_free", 2))
    if free >= keep_free or not bot.config.get_bool("options", "auto_hangar"):
        log.debug("Hangar: %s huecos libres de %s.", free, capacity)
        return
    buttons = panel.find_elements(By.XPATH, ".//button[contains(@onclick, 'mode=upgrade&amount=1&')]")
    if not buttons or "not-active" in (buttons[0].get_attribute("class") or ""):
        log.info("Hangar: %d huecos libres y la ampliación no está disponible ahora (quizá ya hay una en curso).", free)
        return
    # The largest number on the button is the price (a "+1" slot count may come first).
    cost = max((to_int(number) for number in re.findall(r"\d[\d,]*", buttons[0].text)), default=None)
    if not bot.can_spend(cost, "ampliar el hangar"):
        return
    detail = f"hangar +1 hueco por ${fmt(cost)} (quedaban {free} libres de {fmt(capacity)})"
    if bot.dry_run:
        log.info("[SIMULACIÓN] Ampliaría el %s.", detail)
        return
    before = bot.read_money()
    bot.click_element(buttons[0])
    bot.pause(1.0, 1.5)
    if not bot.confirm_purchase(before, cost, "la ampliación del hangar"):
        return
    bot.spent(cost, invest=True)
    bot.count("hangar")
    bot.update_stats(hangar_capacity=(capacity or 0) + 1)
    log.info("Ampliado el %s. Estará listo en unos minutos.", detail)
    bot.notify(f"🏗️ <b>Hangar ampliado</b>: {esc(detail)}.", silent=True)


def plan(bot: "Bot", aircraft: Aircraft, kind: str) -> bool:
    label = "reparación" if kind == "repair" else "A-check"
    panel = bot.ajax(f"maint_plan_do.php?type={kind}&id={aircraft.id}", "maintPlanAction")
    sections = panel.find_elements(By.ID, "typeRepair" if kind == "repair" else "typeCheck")
    if not sections:
        log.warning("%s: el panel de %s no ha cargado.", aircraft.reg, label)
        return False
    section = sections[0]
    cost = section_cost(section)
    buttons = section.find_elements(By.XPATH, _PLAN_BUTTON)
    if not buttons:
        # The game shows a green alert when there is nothing to repair and a red one when the
        # aircraft is away from base (classes instead of text: works in any game language).
        if section.find_elements(By.CSS_SELECTOR, ".alert-success"):
            reason = "ya está reparado del todo"
        elif section.find_elements(By.CSS_SELECTOR, ".alert-danger"):
            reason = "no está en una base ni volando hacia ella"
        else:
            reason = "el juego no ofrece la acción"
        log.info("%s: %s no es posible ahora (%s).", aircraft.reg, label, reason)
        return False
    if not bot.can_spend(cost, f"la {label} de {aircraft.reg}", essential=True):
        return False
    detail = (f"{label} de {aircraft.reg} ({aircraft.model}, desgaste {aircraft.wear:.1f}%, "
              f"{aircraft.hours_to_check} h hasta el check) por ${fmt(cost)}")
    if bot.dry_run:
        log.info("[SIMULACIÓN] Planificaría %s.", detail)
        bot.notify(f"🧪 SIMULACIÓN: planificaría {esc(detail)}.", silent=True)
        return True
    before = bot.read_money()
    bot.click_element(buttons[0])
    response = bot.wait_text("//*[@id='maintPlanActionDo']", timeout=15)
    if not bot.confirm_purchase(before, cost, f"la {label} de {aircraft.reg}", "maintPlanActionDo"):
        return False
    bot.spent(cost)
    bot.count("repairs" if kind == "repair" else "checks")
    log.info("Planificado: %s. %s", detail, clean_response(response))
    bot.notify(f"🔧 <b>Planificado: {esc(detail)}</b>.\n{esc(clean_response(response, 200))}".rstrip())
    return True
