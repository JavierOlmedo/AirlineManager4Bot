"""Marketing campaigns: keep the airline reputation up, because seat occupancy follows it.

Measured on the airline (2026-10-05): reputation 45 % without campaigns and 55 % while the eco-friendly
campaign (+10) was running, and every aircraft flies about as full as the reputation. A campaign therefore
lifts the income of every departure while it runs.

Screen facts (verified 2026-10-05):
* Finances popup (finances.php) -> marketing.php into #financeAction: the reputation stars are followed by
  "(45 %)" (".stars ~ .s-text"); #active-campaigns lists the running campaigns, each with a
  timer('c<id>timer', <seconds left>) call in the page script.
* marketing_new.php?type=1 -> #campaign-2: #dSelector (1..6 = 4, 8, 12, 16, 20, 24 h); the page's own change
  handler writes the cost of campaign N for that duration into #c<N> and marks #c<N>Btn "not-active" when the
  balance is too low. The button calls marketing_new.php?type=1&c=<N>&mode=do&d=<duration> into #marketingStart.
* marketing_new.php?type=5 (eco-friendly, 12 h, +10 reputation, only effective while the airline holds CO2
  quotas) has a single button calling marketing_new.php?type=5&mode=do&c=1.
* While a campaign of a type runs, its page has no mode=do button ("You already have an active campaign").
Everything is located by ids, classes and onclick handlers, so it works with the game in any language.

A campaign is only launched when it pays: its price scales with the fleet size, and in realism, with few
aircraft on long legs, reputation campaign 4 for 8 h cost $234,600 (4 aircraft) for about $100-180k more in
tickets, while the eco-friendly one cost $16,540 for about $50-130k (2026-10-07). The extra revenue is the
gross income per day the bot measures x the hours x the points it adds / the current reputation.
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Optional

from selenium.webdriver.common.by import By

from helpers import clean_response, fmt, to_int
from notify import esc

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.marketing")

REPUTATION = 1   # "Increase airline reputation", campaigns 1-4
ECO = 5          # "Eco-friendly"
DURATION_HOURS = (4, 8, 12, 16, 20, 24)   # #dSelector values 1..6
ECO_HOURS = 12
# Reputation points a campaign adds for sure (the game gives a range: +5-10, +10-18, +18-25, +25-35; eco +10).
ECO_POINTS = 10
REPUTATION_POINTS = {1: 5, 2: 10, 3: 18, 4: 25}
MIN_RETURN = 1.2           # the extra tickets must beat the price by 20 % (more passengers also burn more CO2)
REVENUE_HOURS = 6          # income measured before judging: with 6 h legs one hour can hold a whole departure wave
RECHECK_LATER = 3600       # a campaign that does not pay (or cannot be judged yet) is looked at again in an hour

_DO_BUTTON = ".//button[contains(@onclick, 'mode=do')]"
_REPUTATION_JS = """
const rep = document.querySelector("#financeAction .stars ~ .s-text");
return rep ? rep.textContent : null;
"""
_TIMER_RE = re.compile(r"timer\('[^']*',\s*(\d+)\)")


def duration_value(hours: int) -> tuple[int, int]:
    """(#dSelector value, hours) of the offered duration closest to *hours*."""
    best = min(DURATION_HOURS, key=lambda h: (abs(h - hours), h))
    return DURATION_HOURS.index(best) + 1, best


def campaign_return(revenue_day: float, reputation: float, points: int, hours: float) -> float:
    """Extra ticket revenue of a campaign: aircraft fly about as full as the reputation, so while it runs
    the revenue grows by the points it adds over the current reputation."""
    base = max(10.0, reputation)
    return revenue_day * hours / 24 * (min(100.0, base + points) - base) / base


def run_marketing(bot: "Bot") -> None:
    """Read the reputation and start the enabled campaigns that are not running and pay (cash reserve permitting)."""
    if time.time() < bot.marketing_next_check:
        return  # every enabled campaign is running or does not pay; the bot comes back later
    cfg = bot.config
    wanted = [kind for kind, key in ((ECO, "marketing_eco"), (REPUTATION, "auto_marketing")) if cfg.get_bool("options", key)]
    bot.open_popup("finances.php", "Finances", "nav_finances")
    bot.ajax("marketing.php", "financeAction")
    before = read_reputation(bot)
    states = {}
    reputation = before
    for kind in wanted:
        if bot.stopping:
            break
        states[kind] = start_campaign(bot, kind, reputation)
        if kind == ECO and states[kind] == "started" and reputation is not None:
            reputation += ECO_POINTS  # the reputation campaign is judged on top of the eco one
    if "started" in states.values():
        bot.ajax("marketing.php", "financeAction")
    reputation = read_reputation(bot)
    timers = [int(seconds) for seconds in _TIMER_RE.findall(bot.js(
        "var e = document.getElementById('financeAction'); return e ? e.innerHTML : '';") or "")]
    bot.close_popup()

    ends_in = min(timers) if timers else None
    bot.update_stats(reputation=reputation, campaign_ends=int(time.time() + ends_in) if ends_in else 0)
    if ends_in:
        plural = "s" if len(timers) > 1 else ""
        running = (f"{len(timers)} campaña{plural} activa{plural}, la primera acaba en "
                   f"{ends_in // 3600}:{ends_in % 3600 // 60:02d} h")
        bot.note_event(ends_in, "el fin de una campaña")
    else:
        running = "sin campañas activas"
    change = f" (antes {before} %)" if before is not None and reputation is not None and reputation != before else ""
    log.info("Reputación %s %%%s | %s.", fmt(reputation), change, running)
    # Look again when a campaign ends, within the hour if one does not pay yet, and every cycle if one could
    # not start for lack of money.
    waits = [ends_in] if ends_in else []
    if "later" in states.values():
        waits.append(RECHECK_LATER)
    if wanted and waits and all(state in ("running", "started", "later") for state in states.values()):
        bot.marketing_next_check = time.time() + min(waits)
    else:
        bot.marketing_next_check = 0.0


def read_reputation(bot: "Bot") -> Optional[int]:
    return to_int(bot.js(_REPUTATION_JS))


def start_campaign(bot: "Bot", kind: int, reputation: Optional[int] = None) -> str:
    """Returns 'running' (already active), 'started', 'dry' (dry run), 'later' (does not pay, or the income is not
    known well enough yet to tell) or 'skipped' (money, not green ...)."""
    cfg = bot.config
    bot.js("var c = document.getElementById('campaign-2'); if (c) { c.style.display = 'block'; }")
    page = bot.ajax(f"marketing_new.php?type={kind}", "campaign-2")
    buttons = page.find_elements(By.XPATH, _DO_BUTTON)
    if not buttons:
        return "running"
    if kind == REPUTATION:
        level = max(1, min(4, cfg.get_int("settings", "marketing_campaign", 4)))
        value, hours = duration_value(cfg.get_int("settings", "marketing_hours", 8))
        bot.js("$('#dSelector').val(arguments[0]).trigger('change');", str(value))
        bot.pause(0.4, 0.8)
        cost = to_int(bot.js("var e = document.getElementById(arguments[0]); return e ? e.textContent : null;", f"c{level}"))
        found = page.find_elements(By.ID, f"c{level}Btn")
        button = found[0] if found else None
        what = f"la campaña de reputación {level} ({hours} h)"
        points = REPUTATION_POINTS[level]
    else:
        co2 = bot.stats().co2  # unknown until the market is read; the bot keeps CO2 in stock anyway
        if co2 is not None and co2 <= 0:
            log.info("No lanzo la campaña eco-friendly: solo funciona con cuotas de CO2 en el tanque.")
            return "skipped"
        button = buttons[0]
        cost = to_int(button.get_attribute("textContent"))
        what = "la campaña eco-friendly (12 h, +10 % de reputación)"
        hours, points = ECO_HOURS, ECO_POINTS
    if button is None:
        log.warning("No encuentro el botón de %s.", what)
        return "skipped"
    # Does it pay? Until REVENUE_HOURS of income are measured only the cheap eco-friendly campaign goes ahead.
    revenue = bot.revenue_per_day(REVENUE_HOURS)
    gain = ""
    if not revenue and kind == REPUTATION:
        log.info("Aún no conozco bien los ingresos (los mido %d h): espero para lanzar %s ($%s).",
                 REVENUE_HOURS, what, fmt(cost))
        return "later"
    if revenue and cost:
        current = reputation if reputation else bot.load_factor() * 100
        extra = campaign_return(revenue, current, points, hours)
        if extra < cost * MIN_RETURN:
            log.info("No lanzo %s: cuesta $%s y traería unos $%s más en billetes (ingresos ~$%s/día, reputación %.0f %%).",
                     what, fmt(cost), fmt(int(extra)), fmt(revenue), current)
            return "later"
        gain = f" (traerá unos ${fmt(int(extra))} más en billetes)"
    if "not-active" in (button.get_attribute("class") or ""):
        log.info("El saldo no llega para %s ($%s).", what, fmt(cost))
        return "skipped"
    if not bot.can_spend(cost, what):
        return "skipped"
    if bot.dry_run:
        log.info("[SIMULACIÓN] Lanzaría %s por $%s%s.", what, fmt(cost), gain)
        return "dry"
    before = bot.read_money()
    bot.click_element(button)
    response = bot.wait_loaded("marketingStart", timeout=15, stale=button)
    if not bot.confirm_purchase(before, cost, what, "marketingStart"):
        return "skipped"
    bot.spent(cost)
    bot.count("campaigns")
    bot.count("campaign_spent", cost or 0)
    log.info("Lanzada %s por $%s%s. %s", what, fmt(cost), gain, clean_response(response))
    bot.notify(f"📣 <b>Lanzada {esc(what)}</b> por ${fmt(cost)}{esc(gain)}.")
    return "started"
