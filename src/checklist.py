"""The game's checklist (button at the bottom left): log the open tasks, notice completed ones, collect rewards.

The tasks themselves get done by the rest of the bot (first-class passengers by the seat layout, the cash
balance by the savings goal); this step only keeps an eye on them.

Screen facts (verified 2026-10-05): the main page shows #checklistBtn with the number of open tasks in
#checklistCount; welcome.php loads into #welcomeContent a table with one row per task: the first cell is the
task (with its reward, if any) and the last cell holds ☑ when done or ☐ when open. The rows are read by
structure and by those two symbols, never by text, so this works with the game in any language.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from helpers import to_int
from notify import esc

if TYPE_CHECKING:
    from bot import Bot

log = logging.getLogger("am4bot.checklist")

# The page's counter only refreshes when welcome.php is loaded again, so read the list every hour as well.
CHECK_EVERY = 3600

_COUNTER_JS = """
const button = document.getElementById("checklistBtn"), count = document.getElementById("checklistCount");
return {visible: !!button && getComputedStyle(button).display !== "none", count: count ? count.textContent : null};
"""
_TASKS_JS = """
const root = document.getElementById("welcomeContent");
if (!root) { return null; }
return Array.from(root.querySelectorAll("table tr")).filter(r => r.cells.length >= 2).map(r => {
  const last = r.cells[r.cells.length - 1];
  return {task: r.cells[0].textContent.replace(/\\s+/g, " ").trim(), done: last.textContent.indexOf("\\u2611") >= 0,
          claim: last.querySelectorAll("button, [onclick]").length, id: last.id || null};
});
"""
_CLAIM_JS = """
const root = document.getElementById("welcomeContent");
const targets = root ? Array.from(root.querySelectorAll("table tr td:last-child button, table tr td:last-child [onclick]")) : [];
targets.forEach(t => t.click());
return targets.length;
"""


def check_checklist(bot: "Bot") -> None:
    counter = bot.js(_COUNTER_JS) or {}
    count = to_int(counter.get("count")) if counter.get("visible") else 0
    last = bot.recall("checklist", {})
    if count == last.get("count") and time.time() - float(last.get("checked", 0)) < CHECK_EVERY:
        return
    bot.ajax("welcome.php", "welcomeContent")
    tasks = bot.js(_TASKS_JS) or []
    if not tasks:
        log.debug("No he podido leer el checklist.")
        return
    if any(task["claim"] for task in tasks):
        if bot.dry_run:
            log.info("[SIMULACIÓN] Cobraría las recompensas del checklist.")
        else:
            claimed = bot.js(_CLAIM_JS) or 0
            bot.pause(1.5, 2.0)
            log.info("Checklist: recompensa cobrada (%d botón/es pulsados).", claimed)
            bot.notify("🎁 <b>Checklist</b>: recompensa cobrada.")
            bot.ajax("welcome.php", "welcomeContent")
            tasks = bot.js(_TASKS_JS) or tasks

    open_tasks = [task["task"] for task in tasks if not task["done"]]
    previous = last.get("open")
    for task in previous or []:
        if task not in open_tasks:
            log.info("✅ Checklist: tarea completada «%s».", task)
            bot.notify(f"✅ <b>Checklist</b>: tarea completada «{esc(task)}».")
    if open_tasks != previous:
        if open_tasks:
            log.info("Checklist: %d de %d tareas pendientes: %s.", len(open_tasks), len(tasks),
                     "; ".join(f"«{task}»" for task in open_tasks))
        else:
            log.info("Checklist: ¡todas las tareas completadas!")
    # The ids of the open tasks' cells (claim_7 = first 1st class passenger) tell other steps what is left to do.
    open_ids = [task["id"] for task in tasks if not task["done"] and task.get("id")]
    bot.remember("checklist", {"count": count, "checked": int(time.time()), "open": open_tasks, "open_ids": open_ids})
