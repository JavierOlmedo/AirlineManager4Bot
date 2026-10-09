"""Airline Manager 4 automation: log in, depart, buy fuel / CO2, maintain and grow the fleet.

The bot runs in its own daemon thread. The GUI only reads ``state``, ``stats()``
and ``next_cycle_at``; it never touches the WebDriver. The maintenance and fleet
features live in ``maintenance.py`` and ``fleet.py`` and use the public helpers
of this class (``ajax``, ``js``, ``open_popup`` ...). User-facing messages are
in Spanish; code and comments stay in English.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Optional

from selenium.common.exceptions import (
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from checklist import check_checklist
from config import AppConfig
from driver import create_driver
from fleet import manage_fleet
from gamemode import EASY, GameMode, from_difficulty
from helpers import first_int, fmt, fmt_duration, timer_seconds, to_int
from economy import (add_money_sample, fmt_days, fmt_money, goal_progress, income_per_day, revenue_per_day, state_file,
                     usage_per_day)
from maintenance import run_maintenance
from market import PriceHistory, chart_prices
from marketing import run_marketing
from notify import Telegram, esc
from seats import optimize_seats

# One logger per topic: the GUI colours and tags the log lines by the logger suffix (see helpers.LOG_TAGS).
log = logging.getLogger("am4bot.bot")
log_login = logging.getLogger("am4bot.login")
log_money = logging.getLogger("am4bot.dinero")
log_flights = logging.getLogger("am4bot.vuelos")
log_telegram = logging.getLogger("am4bot.telegram")

# Fuel and CO2 prices change every 30 minutes: buy at most once per price window.
PRICE_WINDOW_SECONDS = 1800

COUNTER_KEYS = ("fuel_bought", "fuel_spent", "co2_bought", "co2_spent", "departures", "routes", "aircraft", "repairs", "checks",
                "hangar", "campaigns", "campaign_spent", "seats", "seats_spent", "mods", "mods_spent")

# A game fragment has finished loading when its container has content and no loader image.
_LOADED_JS = ("var e = document.getElementById(arguments[0]);"
              "return !!e && e.innerHTML.trim().length > 0 && !e.querySelector(\"img[src*='loader']\");")

# Text fallbacks for the market popup: "HOLDING 2,672,750 Lbs", "CAPACITY 3,327,250 / 6,000,000 Lbs"
# (the first capacity number is the free space, the second the total).
_HOLDING_RE = re.compile(r"holding\D{0,20}([\d.,]+)", re.I)
_CAPACITY_RE = re.compile(r"capacity\D{0,20}([\d.,]+)\s*/\s*([\d.,]+)", re.I)
_PRICE_RE = re.compile(r"\$\s*([\d.,]+)")

# Recoverable Selenium errors: log them and carry on with the next step.
_SOFT_ERRORS = (TimeoutException, NoSuchElementException, StaleElementReferenceException, JavascriptException)


def _mask_email(email: str) -> str:
    """'pilot@example.com' -> 'pi***@example.com' so the log file never holds the full account name."""
    name, _, domain = email.partition("@")
    return f"{name[:2]}***@{domain}" if domain else f"{name[:2]}***"


class BotState(str, Enum):
    IDLE = "Parado"
    STARTING = "Abriendo navegador"
    LOGGING_IN = "Iniciando sesión"
    RUNNING = "En marcha"
    STOPPING = "Parando"
    ERROR = "Error"


@dataclass
class Stats:
    money: Optional[int] = None
    points: Optional[int] = None
    fuel: Optional[int] = None
    fuel_capacity: Optional[int] = None
    fuel_price: Optional[int] = None
    co2: Optional[int] = None
    co2_capacity: Optional[int] = None
    co2_price: Optional[int] = None
    fuel_buy_at: Optional[int] = None
    co2_buy_at: Optional[int] = None
    fleet_size: Optional[int] = None
    parked: Optional[int] = None
    pending: Optional[int] = None
    inflight: Optional[int] = None
    hangar_free: Optional[int] = None
    hangar_capacity: Optional[int] = None
    income_day: Optional[int] = None
    goal_price: Optional[int] = None
    reputation: Optional[int] = None
    campaign_ends: Optional[int] = None   # epoch of the first running campaign's end, 0 = none running
    mode: Optional[str] = None            # game mode label: "fácil" / "realista"
    updated_at: Optional[float] = None


class Bot:
    def __init__(self, config: AppConfig):
        self.config = config
        self.driver: Optional[WebDriver] = None
        self.state = BotState.IDLE
        self.last_error: Optional[str] = None
        self.next_cycle_at: Optional[float] = None

        self._stats = Stats()
        self._stats_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.history = PriceHistory()
        self._dry_windows: dict[str, int] = {}
        self.telegram = Telegram()
        # Earliest event worth waking up for before the regular interval: (seconds, description)
        self._next_event: Optional[tuple[int, str]] = None
        # Persistent counters for the daily summary and the date it was last sent.
        self._state: dict = self._load_state()
        # Maintenance fleet list of this cycle (who is at the base), reused by the seat step.
        self._fleet_cache: Optional[tuple[float, list]] = None
        # While every enabled campaign runs, the marketing page is only checked again when the first one ends.
        self.marketing_next_check = 0.0
        # Easy or realism: flight speed and ticket formulas used by the profit estimates (read every cycle).
        self.mode: GameMode = EASY
        # The game account follows the interface language: checked once per run and after every change.
        self._language_checked = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self.last_error = None
        self.marketing_next_check = 0.0
        self._language_checked = False
        self._thread = threading.Thread(target=self._run, name="am4bot", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self.is_alive():
            self.state = BotState.STOPPING
        self._stop.set()
        self._wake.set()

    def run_now(self) -> None:
        """Skip the remaining wait and start the next cycle immediately."""
        self._wake.set()

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def kill_browser(self) -> None:
        """Last resort on shutdown when the bot thread does not finish in time."""
        self._quit_driver()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    @property
    def dry_run(self) -> bool:
        return self.config.get_bool("options", "dry_run")

    # ------------------------------------------------------------------ stats and money
    def stats(self) -> Stats:
        with self._stats_lock:
            return replace(self._stats)

    def update_stats(self, **values: Optional[int]) -> None:
        with self._stats_lock:
            for key, value in values.items():
                if value is not None:
                    setattr(self._stats, key, value)
            self._stats.updated_at = time.time()

    def can_spend(self, cost: Optional[int], what: str, essential: bool = False) -> bool:
        """True when *cost* fits the balance minus the configured cash reserve.

        The reserve is the cushion for what keeps the fleet flying: *essential* spending (repairs, A-checks,
        the route of an aircraft already bought) may use it, everything else stays above it.
        """
        if cost is None:
            log_money.warning("No he podido leer el coste de %s, lo salto.", what)
            return False
        money = self.stats().money
        if money is None:
            log_money.warning("Saldo desconocido, salto %s.", what)
            return False
        reserve = 0 if essential else self.config.get_int("settings", "cash_reserve", 0)
        if money - cost < reserve:
            if essential:
                log_money.info("Salto %s: cuesta $%s y el saldo es $%s.", what, fmt(cost), fmt(money))
            else:
                log_money.info("Salto %s: $%s dejaría el saldo por debajo de la reserva de $%s (saldo $%s).",
                               what, fmt(cost), fmt(reserve), fmt(money))
            return False
        return True

    def spent(self, cost: Optional[int], invest: bool = False) -> None:
        """Lower the cached balance until the header is read again.

        *invest* marks aircraft, route fees and hangar slots: they are added back when the
        income rate is estimated, so buying an aircraft does not look like a bad day.
        """
        money = self.stats().money
        if cost and money is not None:
            self.update_stats(money=max(0, money - cost))
        if cost:
            # Every expense also goes into a running total: money change + spending = gross income (marketing.py).
            self._state["spent_total"] = int(self._state.get("spent_total", 0)) + int(cost)
            if invest:
                self._state["invested"] = int(self._state.get("invested", 0)) + int(cost)
            self._save_state()

    def fuel_cost_basis(self) -> int:
        """Fuel price used to rank aircraft: what the bot actually pays (its buy threshold), not today's spike."""
        stats = self.stats()
        return stats.fuel_buy_at or stats.fuel_price or self.config.get_int("settings", "fuel_price_good", 800) or 800

    def co2_cost_basis(self) -> int:
        """CO2 price used in the estimates: the bot's buy threshold."""
        return self.stats().co2_buy_at or self.config.get_int("settings", "co2_price_good", 120) or 120

    def stock_price(self, kind: str) -> float:
        """Average price paid for the fuel / CO2 in the tank ($ per 1,000), the buy threshold until the first purchase."""
        paid = self._state.get("stock_price", {}).get(kind)
        return float(paid) if paid else float(self.fuel_cost_basis() if kind == "fuel" else self.co2_cost_basis())

    def income_per_day(self) -> Optional[int]:
        """Net income per day, with fuel and CO2 counted when burnt (at the average price paid for them)."""
        stats = self.stats()
        return income_per_day(self._state, self.stock_price("fuel") if stats.fuel is not None else None,
                              self.stock_price("co2") if stats.co2 is not None else None)

    def revenue_per_day(self, min_hours: float = 1) -> Optional[int]:
        """Gross income per day (ticket sales): what a campaign multiplies. None until *min_hours* are measured."""
        return revenue_per_day(self._state, int(min_hours * 3600))

    def usage_per_day(self, kind: str) -> Optional[int]:
        """Fuel or CO2 the fleet burns per day, measured from the tank readings."""
        return usage_per_day(self._state, kind)

    def _stock_limit(self, use: Optional[int], excellent: bool) -> Optional[int]:
        """Most fuel / CO2 worth holding: stock_days of the measured use, twice that at an exceptional price.
        None = no limit (stock_days 0, or the use is not measured yet)."""
        days = self.config.get_int("settings", "stock_days", 3)
        if days <= 0 or not use:
            return None
        return use * days * (2 if excellent else 1)

    def load_factor(self) -> float:
        """Average seat occupancy measured on the airline's own flights (default 55 % until measured)."""
        value = self._state.get("load_factor")
        return float(value) if isinstance(value, (int, float)) and 0.1 <= value <= 1 else 0.55

    def record_load(self, measured: float) -> None:
        """Smooth the measured occupancy (it changes slowly, with the airline reputation)."""
        current = self._state.get("load_factor")
        value = measured if not isinstance(current, (int, float)) else 0.8 * current + 0.2 * measured
        self._state["load_factor"] = round(max(0.1, min(1.0, value)), 3)
        self._save_state()
        log_flights.debug("Ocupación medida %.0f %% (media %.0f %%).", measured * 100, value * 100)

    # ------------------------------------------------------------------ notifications and counters
    def notify(self, text: str, silent: bool = False) -> None:
        """Send a Telegram message (HTML) when notifications are enabled and configured."""
        if self.config.get_bool("options", "telegram") and self.telegram.enabled:
            profile = self.config.profile
            # With several airlines on the same chat, say which one is talking.
            self.telegram.send(text if profile.is_main else f"[{esc(profile.label)}] {text}", silent)

    def count(self, key: str, amount: int = 1) -> None:
        counters = self._state.setdefault("counters", {})
        counters[key] = int(counters.get(key, 0)) + amount
        self._save_state()

    def recall(self, key: str, default=None):
        """A value the feature modules keep in data/state.json between runs."""
        return self._state.get(key, default)

    def remember(self, key: str, value) -> None:
        self._state[key] = value
        self._save_state()

    def cache_fleet(self, fleet: list) -> None:
        self._fleet_cache = (time.time(), fleet)

    def recent_fleet(self, max_age: float = 300) -> Optional[list]:
        """The maintenance fleet list read in the last few minutes, if any."""
        if self._fleet_cache and time.time() - self._fleet_cache[0] <= max_age:
            return self._fleet_cache[1]
        return None

    def _update_price_record(self, kind: str, tlog: logging.Logger) -> None:
        """Keep the lowest price ever seen and when (the price history itself only keeps 14 days)."""
        series = self.history.series(kind)
        if not series:
            return
        t, price = min(series, key=lambda item: (item[1], -item[0]))
        records = self._state.setdefault("price_records", {})
        best = records.get(kind)
        if best is None or price < best[0]:
            records[kind] = [int(price), int(t)]
            self._save_state()
            if best is not None:
                tlog.info("¡Nuevo mínimo de %s: $%s (antes $%s)!", "CO2" if kind == "co2" else "fuel", fmt(price), fmt(best[0]))

    def _bought_in_window(self, kind: str, window: int) -> bool:
        # Persisted so that a restart inside the same 30-minute price window does not buy twice.
        if self._dry_windows.get(kind) == window:
            return True
        return int(self._state.get("last_buy_window", {}).get(kind, -1)) == window

    def _mark_bought(self, kind: str, window: int) -> None:
        if self.dry_run:  # a simulated purchase must not block a real one after switching the simulation off
            self._dry_windows[kind] = window
            return
        self._state.setdefault("last_buy_window", {})[kind] = window
        self._save_state()

    def _load_state(self) -> dict:
        try:
            state = json.loads(state_file().read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        try:
            path = state_file()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._state, indent=1), encoding="utf-8")
        except OSError:
            pass

    def _maybe_daily_summary(self) -> None:
        """Once a day, after `summary_hour`, send the balance, stocks, fleet and the day's actions."""
        hour = max(0, min(23, self.config.get_int("settings", "summary_hour", 9)))
        now = time.localtime()
        today = time.strftime("%Y-%m-%d", now)
        if now.tm_hour < hour or self._state.get("last_summary_date") == today:
            return
        stats = self.stats()
        counters = {key: int(self._state.get("counters", {}).get(key, 0)) for key in COUNTER_KEYS}
        start = self._state.get("money_day_start")
        delta = ""
        if stats.money is not None and isinstance(start, int):
            diff = stats.money - start
            delta = f" ({'+' if diff >= 0 else '-'}${fmt(abs(diff))} desde el último resumen)"
        lines = [
            f"📊 <b>Resumen diario</b> {time.strftime('%d/%m/%Y', now)}",
            f"💰 Saldo: ${fmt(stats.money)}{esc(delta)}",
            f"⛽ Fuel: {fmt(stats.fuel)} / {fmt(stats.fuel_capacity)} a ${fmt(stats.fuel_price)} | comprado {fmt(counters['fuel_bought'])} lbs (${fmt(counters['fuel_spent'])})",
            f"🌿 CO2: {fmt(stats.co2)} / {fmt(stats.co2_capacity)} a ${fmt(stats.co2_price)} | comprado {fmt(counters['co2_bought'])} cuotas (${fmt(counters['co2_spent'])})",
            f"✈️ Flota: {fmt(stats.fleet_size)} aviones, {fmt(stats.inflight)} volando, {fmt(stats.parked)} aparcados | despegues: {counters['departures']}",
            f"🛫 Rutas creadas: {counters['routes']} | 🛒 Aviones pedidos: {counters['aircraft']} | 🔧 Reparaciones: {counters['repairs']}, A-checks: {counters['checks']}",
        ]
        if stats.reputation is not None or counters["campaigns"] or counters["seats"]:
            lines.append(f"📣 Reputación: {fmt(stats.reputation)} % | campañas: {counters['campaigns']} (${fmt(counters['campaign_spent'])})"
                         f" | 💺 cambios de asientos: {counters['seats']} (${fmt(counters['seats_spent'])})"
                         f" | 🛠️ mejoras: {counters['mods']} (${fmt(counters['mods_spent'])})")
        if stats.income_day is not None:
            lines.append(f"📈 Ingresos netos estimados: ~${fmt(stats.income_day)}/día")
        goal = self.config.get("settings", "goal_model")
        if self.config.get_bool("options", "save_for_goal") and goal and stats.goal_price:
            progress = goal_progress(stats.goal_price, stats.money, self.config.get_int("settings", "cash_reserve", 0), stats.income_day)
            if progress:
                lines.append(f"🎯 Objetivo {esc(goal)}: {progress['pct']:.0f}% ({fmt_money(progress['have'])} de "
                             f"{fmt_money(stats.goal_price)}), llegada {fmt_days(progress['eta_days'])}")
        if self.dry_run:
            lines.append("🧪 La simulación está activada: no se ha comprado ni planificado nada de verdad.")
        self.notify("\n".join(lines))
        log_telegram.info("Resumen diario enviado.")
        self._state["last_summary_date"] = today
        self._state["money_day_start"] = stats.money
        self._state["counters"] = {}
        self._save_state()

    # ------------------------------------------------------------------ main loop
    def _run(self) -> None:
        try:
            self.state = BotState.STARTING
            self.config.reload_secrets()
            self.telegram = Telegram(*self.config.telegram)
            if self.config.get_bool("options", "telegram") and not self.telegram.enabled:
                log_telegram.info("Las notificaciones están activadas pero faltan bot_token / chat_id en config/secrets.ini.")
            self.notify(f"🟢 <b>Bot iniciado</b>{' (simulación)' if self.dry_run else ''}", silent=True)
            log.info("Abriendo Chrome ...")
            self.driver = create_driver(
                url=self.config.get("app", "url", "https://www.airlinemanager.com/"),
                keep_session=self.config.get_bool("options", "keep_session"),
                headless=self.config.get_bool("options", "headless"),
            )
            self.state = BotState.LOGGING_IN
            if not self._login():
                raise RuntimeError("El inicio de sesión falló o agotó el tiempo")
            self.state = BotState.RUNNING
            while not self._stop.is_set():
                self._cycle()
                if self._stop.is_set():
                    break
                self._sleep_until_next_cycle()
        except Exception as exc:  # noqa: BLE001 - every failure must reach the GUI log
            if self._stop.is_set():
                log.info("Bot parado.")
                self.notify("⏹ Bot parado.", silent=True)
            else:
                self.state = BotState.ERROR
                self.last_error = (str(exc).splitlines() or [exc.__class__.__name__])[0]
                log.error("El bot se ha detenido por un error: %s", self.last_error)
                log.debug("Traceback:", exc_info=True)
                self.notify(f"🔴 <b>Bot detenido por un error</b>: {esc(self.last_error)}")
        else:
            log.info("Bot parado.")
            self.notify("⏹ Bot parado.", silent=True)
        finally:
            self._quit_driver()
            self.next_cycle_at = None
            if self.state is not BotState.ERROR:
                self.state = BotState.IDLE

    def _cycle(self) -> None:
        self._ensure_session()
        opt = lambda key: self.config.get_bool("options", key)  # noqa: E731
        log.info("Revisando la aerolínea ...%s", " [SIMULACIÓN: no se compra ni se planifica nada]" if self.dry_run else "")
        self._next_event = None
        self._guard(self._check_tutorial, "comprobar el tutorial")
        self._guard(self._read_mode, "leer el modo de juego")
        if not self._language_checked and self.config.get_bool("options", "sync_game_language", True):
            self._guard(self._sync_game_language, "cambiar el idioma del juego")
        self._guard(self._read_header, "leer dinero y puntos")
        self._guard(self._read_flights, "leer la lista de vuelos")
        # Campaigns go before departures: the passengers of a flight are counted when it departs.
        if opt("auto_marketing") or opt("marketing_eco"):
            self._guard(lambda: run_marketing(self), "revisar las campañas de marketing")
        # Maintenance and seat changes go before departures: a landed aircraft can only be repaired,
        # checked or modified while it sits at the base, so plan it before "Depart all" sends it away again.
        if opt("auto_repair") or opt("auto_check"):
            self._guard(lambda: run_maintenance(self), "planificar mantenimiento")
        if opt("auto_seats") or self.config.get_bool("options", "auto_mods", True):
            self._guard(lambda: optimize_seats(self), "revisar el taller (asientos y mejoras)")
        if opt("auto_depart"):
            self._guard(self._depart_all, "despegar aviones")
        if opt("autobuy_fuel") or opt("autobuy_co2"):
            self._guard(self._check_market, "revisar el mercado de fuel / CO2")
        if opt("auto_route") or opt("autobuy_aircraft"):
            self._guard(lambda: manage_fleet(self), "gestionar la flota")
        if opt("auto_checklist"):
            self._guard(lambda: check_checklist(self), "revisar el checklist")
        self._guard(self._maybe_daily_summary, "enviar el resumen diario")

    def _guard(self, action: Callable[[], None], what: str) -> None:
        try:
            action()
        except _SOFT_ERRORS as exc:
            log.warning("Problema al %s: %s. Lo dejo para el siguiente ciclo.", what, exc.__class__.__name__)
            log.debug("Detalles:", exc_info=True)
            self.close_popup(quiet=True)

    def _sleep_until_next_cycle(self) -> None:
        low = max(1, self.config.get_int("settings", "cycle_min_minutes", 5))
        high = max(low, self.config.get_int("settings", "cycle_max_minutes", 10))
        seconds = random.uniform(low * 60, high * 60)
        reason = ""
        if self._next_event is not None and self._next_event[0] + 20 < seconds:
            seconds = max(60.0, self._next_event[0] + 20)
            reason = f" (me adelanto por {self._next_event[1]})"
        self.next_cycle_at = time.time() + seconds
        log.info("Próxima revisión en %d min %02d s%s.", seconds // 60, seconds % 60, reason)
        self._wake.wait(seconds)
        self._wake.clear()
        self.next_cycle_at = None

    def note_event(self, seconds: Optional[int], what: str) -> None:
        """Remember the earliest upcoming event (landing, price change) to shorten the next wait."""
        if seconds is None or seconds < 0:
            return
        if self._next_event is None or seconds < self._next_event[0]:
            self._next_event = (int(seconds), what)

    def _ensure_session(self) -> None:
        # Raises WebDriverException (fatal) when the user closed the browser.
        self.driver.current_url
        if self._is_logged_in(timeout=5):
            return
        log_login.warning("Sesión perdida, vuelvo a iniciar sesión ...")
        self.state = BotState.LOGGING_IN
        self.driver.get(self.config.get("app", "url", "https://www.airlinemanager.com/"))
        if not self._login():
            raise RuntimeError("No he podido volver a iniciar sesión")
        self.state = BotState.RUNNING

    # ------------------------------------------------------------------ login
    def _login(self) -> bool:
        if self._is_logged_in(timeout=5):
            log_login.info("Sesión ya iniciada (restaurada).")
            return True

        username, password = self.config.credentials
        timeout = max(30, self.config.get_int("settings", "login_timeout", 300))

        if username and password:
            log_login.info("Iniciando sesión como %s ...", _mask_email(username))
            self._open_login_form()
            self._type(self._sel("login_email"), username)
            self._type(self._sel("login_password"), password)
            remember = self._find(self._sel("login_remember"), timeout=5)
            if remember is not None and not remember.is_selected():
                self.pause()
                self.click_element(remember)  # styled checkbox: the input itself is not clickable
            self._click(self._sel("login_submit"))
        else:
            log_login.warning("Sin credenciales: inicia sesión a mano en la ventana de Chrome.")

        started = time.time()
        warned = False
        while not self._stop.is_set() and time.time() - started < timeout:
            if self._is_logged_in(timeout=3):
                log_login.info("Sesión iniciada.")
                return True
            if not warned and time.time() - started > 20:
                log_login.warning(
                    "Todavía sin sesión. Si la web muestra un captcha o un error, termina el login a mano "
                    "(espero hasta %d s).",
                    timeout,
                )
                warned = True
            self._stop.wait(2)
        return False

    def _is_logged_in(self, timeout: float) -> bool:
        if self._find(self._sel("money"), timeout=timeout) is None:
            return False
        # The landing page keeps a hidden login form in the DOM; the game page has none.
        return not self.driver.find_elements(By.XPATH, self._sel("login_form"))

    def _open_login_form(self) -> None:
        try:
            # Same call the site's own "Log in" button makes.
            self.js("login('show');")
        except JavascriptException:
            self._click("//button[contains(@onclick, \"signup('show')\")]")
            self._click("//button[contains(@onclick, \"login('show')\")]")
        WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, self._sel("login_email")))
        )

    # ------------------------------------------------------------------ actions
    def _check_tutorial(self) -> None:
        # While the in-game tutorial is active (global `intro` > 0) the site's Ajax()
        # helper silently drops most actions, so departures and purchases would be no-ops.
        intro = self.js("return (typeof intro === 'undefined') ? null : Number(intro);")
        if intro:
            log.warning(
                "El tutorial del juego está activo (intro=%s): la web ignora despegues y compras hasta "
                "terminarlo. Complétalo o ciérralo en la ventana del navegador.",
                intro,
            )

    def request_game_language(self) -> None:
        """The interface language changed: put the game account in the same language at the next check."""
        self._language_checked = False

    def _sync_game_language(self) -> None:
        # Game settings popup: #langSelection (es, en, fr ...) and #btnSave send every setting with the language.
        wanted = self.config.get("app", "language", "es") or "es"
        self._language_checked = True  # one attempt per run / change, whatever happens
        self.open_popup("user_settings.php", "Settings", "nav_settings")
        current = self.js("var s = document.getElementById('langSelection'); return s ? s.value : null;")
        if current is None:
            log.warning("No encuentro el selector de idioma en los ajustes del juego.")
            self.close_popup()
            return
        if current == wanted:
            log.debug("El juego ya está en el idioma de la interfaz (%s).", wanted)
            self.close_popup()
            return
        if self.dry_run:
            log.info("[SIMULACIÓN] Cambiaría el idioma del juego de «%s» a «%s».", current, wanted)
            self.close_popup()
            return
        self.js("$('#langSelection').val(arguments[0]).trigger('change'); $('#btnSave').click();", wanted)
        self._stop.wait(3)
        self.driver.get(self.config.get("app", "url", "https://www.airlinemanager.com/"))  # the page reloads in the new language
        if self._is_logged_in(timeout=20):
            log.info("Idioma del juego cambiado de «%s» a «%s».", current, wanted)
        else:
            self._language_checked = False
            log.warning("He cambiado el idioma del juego, pero la página no ha vuelto a cargar; lo compruebo en la "
                        "próxima revisión.")

    def _read_mode(self) -> None:
        # The page's `difficulty` is the flight speed multiplier: 1.5 in easy mode, 1 in realism (gamemode.py).
        mode = from_difficulty(self.js("return typeof difficulty === 'undefined' ? null : difficulty;"))
        if mode is None:
            return
        if mode is not self.mode or self.stats().mode is None:
            log.info("Modo de juego: %s (los vuelos van a x%s la velocidad del avión).", mode.label, f"{mode.speed:g}")
        self.mode = mode
        self.update_stats(mode=mode.label)

    def _read_header(self) -> None:
        money = to_int(self._text(self._sel("money"), timeout=5))
        points = to_int(self._text(self._sel("points"), timeout=3))
        self.update_stats(money=money, points=points)
        stats = self.stats()
        if money is not None and add_money_sample(self._state, money, fuel=stats.fuel, co2=stats.co2):
            self._save_state()
        rate = self.income_per_day()
        self.update_stats(income_day=rate)
        rate_note = f" | ingresos netos ~${fmt(rate)}/día" if rate is not None else ""
        log_money.info("Dinero: $%s | Puntos: %s%s", fmt(money), fmt(points), rate_note)

    def _read_flights(self) -> None:
        # The status list keeps a live countdown per in-flight aircraft even while hidden.
        texts = self.js(
            "return Array.from(document.querySelectorAll('#inflightList .countdown_amount')).map(e => e.textContent);"
        ) or []
        remaining = [seconds for seconds in (timer_seconds(t) for t in texts) if seconds is not None]
        self.update_stats(inflight=len(texts))
        if remaining:
            self.note_event(min(remaining), "el próximo aterrizaje")
            log_flights.info("%d aviones en vuelo, próximo aterrizaje en %s.", len(texts), fmt_duration(min(remaining)))

    def _depart_all(self) -> None:
        self.open_popup("routes_main.php", "Routes", "nav_routes")
        button = self._find(self._sel("depart_all"), timeout=5)
        if button is None:
            log_flights.info("Ningún avión listo para despegar.")
        elif not button.is_displayed() or not button.is_enabled() or "not-active" in (button.get_attribute("class") or ""):
            log_flights.info("Nada que despegar ahora mismo.")
        else:
            self.pause()
            button.click()
            log_flights.info("Todos los aviones han despegado.")
            self.count("departures")
            if self.config.get_bool("options", "telegram_departures"):
                self.notify("✈️ Aviones despegados.", silent=True)
            self._stop.wait(2)
        self.close_popup()

    def _check_market(self) -> None:
        self.open_popup("fuel.php", "Fuel", "nav_fuel")
        if self.config.get_bool("options", "autobuy_fuel"):
            self._trade("fuel")
        if self.config.get_bool("options", "autobuy_co2"):
            self._click(self._sel("co2_tab"))
            WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, self._sel("co2_main")))
            )
            self._trade("co2")
        self.close_popup()

    def _trade(self, kind: str) -> None:
        label = "CO2" if kind == "co2" else "fuel"
        tlog = logging.getLogger(f"am4bot.{kind}")
        panel = self._find(self._sel(f"{kind}_main"), timeout=10)
        if panel is None:
            tlog.warning("No encuentro el panel de %s.", label)
            return
        panel_text = panel.text

        price = to_int(self._text(self._sel(f"{kind}_price"), timeout=5))
        if price is None:
            price = first_int(_PRICE_RE, panel_text)
        holding = to_int(self._text(self._sel(f"{kind}_holding"), timeout=2))
        free = to_int(self._text(self._sel(f"{kind}_free"), timeout=2))
        if holding is None:
            holding = first_int(_HOLDING_RE, panel_text)
        if holding is not None and free is not None:
            capacity: Optional[int] = holding + free
        else:
            capacity = first_int(_CAPACITY_RE, panel_text, group=2)
            if free is None and holding is not None and capacity is not None:
                free = capacity - holding
        change_in = timer_seconds(self._text(self._sel(f"{kind}_timer"), timeout=2))
        self.update_stats(**{f"{kind}_price": price, kind: holding, f"{kind}_capacity": capacity})
        self.note_event(change_in, f"el cambio de precio de {label}")

        if price is None:
            tlog.warning("No he podido leer el precio de %s.", label)
            return

        # --- price history: the popup embeds the last 10 prices (one per 30-minute window)
        # The timer only shows whole seconds, so round to the nearest window boundary instead of flooring
        # (flooring sometimes filed the whole series one window too early).
        raw_start = time.time() - (PRICE_WINDOW_SECONDS - change_in) if change_in is not None else time.time()
        window_start = round(raw_start / PRICE_WINDOW_SECONDS) * PRICE_WINDOW_SECONDS if change_in is not None else raw_start
        series = chart_prices(self.driver.find_element(By.XPATH, self._sel("popup_content")).get_attribute("innerHTML"), kind)
        if series:
            self.history.add_series(kind, series, window_start)
        else:
            self.history.add(kind, price, window_start)
        self.history.save()
        self._update_price_record(kind, tlog)

        # --- buy threshold: the fixed "good price", raised by the history percentile when smart buy is on
        buy_at = self.config.get_int("settings", f"{kind}_price_good")
        excellent_at: Optional[int] = None
        history_note = ""
        if self.config.get_bool("options", "smart_buy"):
            days = max(1, self.config.get_int("settings", "history_days", 3))
            pct = self.config.get_int("settings", "buy_percentile", 25)
            summary = self.history.summary(kind, days, pct)
            if summary:
                buy_at = max(buy_at, summary["threshold"])
                top_pct = self.config.get_int("settings", "excellent_percentile", 10)
                if top_pct > 0:
                    excellent_at = self.history.summary(kind, days, min(top_pct, pct))["threshold"]
                history_note = (f" | histórico {days}d: mín {fmt(summary['min'])}, p{pct} {fmt(summary['threshold'])}, "
                                f"mediana {fmt(summary['median'])} ({summary['samples']} muestras)")
            else:
                history_note = f" | histórico corto ({len(self.history.recent(kind, days))} muestras), uso el precio fijo"
        self.update_stats(**{f"{kind}_buy_at": buy_at})

        quantity = self.config.get_int("settings", f"{kind}_quantity_buy")
        use = self.usage_per_day(kind)
        storage = f" | tanque {fmt(holding)} / {fmt(capacity)}" if holding is not None and capacity is not None else ""
        if storage and use:
            storage += f", para ~{holding / use:.1f} días"
        timer = f" | el precio cambia en {change_in // 60:02d}:{change_in % 60:02d}" if change_in is not None else ""
        tlog.info("Precio %s: $%s (compro a <= $%s)%s%s%s", label, fmt(price), fmt(buy_at), storage, timer, history_note)

        # --- how much: fill up at a good price, otherwise only top up a dangerously low stock.
        # An exceptional price (lowest percentile of the history) buys everything the tank and the
        # cash above the reserve allow, and may buy again in the same window as income comes in.
        # Either way never more than stock_days of what the fleet burns (twice that at an exceptional
        # price): money sitting in a tank for weeks earns less than another aircraft.
        reason = ""
        excellent = excellent_at is not None and price <= excellent_at
        topping_up = False
        if price <= buy_at and quantity > 0:
            target = quantity if free is None else min(quantity, free)
            reason = "precio excepcional" if excellent else "buen precio"
            limit = self._stock_limit(use, excellent)
            if limit is not None and holding is not None:
                if holding >= limit:
                    tlog.info("No compro %s (%s): ya tengo para ~%.1f días y el límite es %.0f días de consumo.",
                              label, reason, holding / use, limit / use)
                    return
                target = min(target, limit - holding)
        else:
            min_stock_pct = self.config.get_int("settings", "min_stock_pct", 0)
            if holding is None or capacity is None or min_stock_pct <= 0 or holding * 100 >= capacity * min_stock_pct:
                return
            target = capacity * min_stock_pct // 100 - holding
            reason = f"stock por debajo del {min_stock_pct}%"
            topping_up = True
        if target <= 0:
            tlog.info("El tanque de %s está lleno, nada que comprar.", label)
            return
        window = int(time.time() // PRICE_WINDOW_SECONDS)
        if self._bought_in_window(kind, window) and not excellent:
            tlog.info("%s ya comprado en esta ventana de precio.", label.capitalize())
            return
        money = self.stats().money
        if money is not None:
            # Topping up a nearly empty tank keeps the aircraft flying: it may use the reserve.
            reserve = 0 if topping_up else self.config.get_int("settings", "cash_reserve", 0)
            spend_pct = 100 if excellent or topping_up else self.config.get_int("settings", "market_max_spend_pct", 100)
            spendable = max(0, money - reserve) * max(1, min(spend_pct, 100)) // 100
            affordable = int(spendable * 1000 // price)  # prices are per 1,000 units
            if affordable < 1000:
                if not self._bought_in_window(kind, window):
                    tlog.info("No compro %s: los $%s que quedan sobre la reserva no dan (%s).", label, fmt(max(0, money - reserve)), reason)
                return
            target = min(target, affordable)
        quantity = target
        cost = price * quantity // 1000
        icon = "🌿" if kind == "co2" else "⛽"
        if self.dry_run:
            tlog.info("[SIMULACIÓN] Compraría %s %s a $%s (unos $%s, %s).", fmt(quantity), label, fmt(price), fmt(cost), reason)
            self.notify(f"🧪 SIMULACIÓN: compraría {fmt(quantity)} {label} a ${fmt(price)} (unos ${fmt(cost)}, {esc(reason)}).", silent=True)
            self._mark_bought(kind, window)
            return

        amount = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, self._sel(f"{kind}_amount")))
        )
        self.pause()
        amount.clear()
        amount.send_keys(str(quantity))
        self._click(self._sel(f"{kind}_buy"))
        self._mark_bought(kind, window)
        bought = self._state.setdefault("bought", {})  # running total, for the measured use per day
        bought[kind] = int(bought.get(kind, 0)) + quantity
        paid = self._state.setdefault("stock_price", {})  # average price of what is in the tank
        if holding:
            paid[kind] = round((holding * self.stock_price(kind) + quantity * price) / (holding + quantity), 1)
            self.update_stats(**{kind: holding + quantity})
        else:
            paid[kind] = price
            if holding is not None:
                self.update_stats(**{kind: quantity})
        self.spent(cost)
        self.count(f"{kind}_bought", quantity)
        self.count(f"{kind}_spent", cost)
        tlog.info("Comprado: %s %s a $%s (unos $%s, %s).", fmt(quantity), label, fmt(price), fmt(cost), reason)
        self.notify(f"{icon} <b>Comprado: {fmt(quantity)} {label}</b> a ${fmt(price)} (unos ${fmt(cost)}, {esc(reason)}).")
        self._stop.wait(1.5)

    # ------------------------------------------------------------------ page helpers (used by fleet.py / maintenance.py)
    def open_popup(self, url: str, title: str, nav_selector: str) -> None:
        """Open one of the game's modal popups, preferably by clicking its nav button."""
        nav_xpath = self.config.get("selectors", nav_selector)
        button = self._find(nav_xpath, timeout=3) if nav_xpath else None
        if button is not None:
            self.pause()
            try:
                button.click()
            except WebDriverException:
                self.js("arguments[0].click();", button)
        else:
            log.debug("No encuentro el botón '%s', abro %s con el helper popup() de la web.", nav_selector, url)
            self.js("popup(arguments[0], arguments[1], false, true);", url, title)

        content = self._sel("popup_content")
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.visibility_of_element_located((By.XPATH, content)))
        wait.until(lambda d: not d.find_elements(By.XPATH, content + "//img[contains(@src, 'loader')]"))
        self._stop.wait(0.5)

    def close_popup(self, quiet: bool = False) -> None:
        try:
            self.js(
                "if (window.jQuery) { if ($('#popup').length) { $('#popup').modal('hide'); } "
                "if ($('#newRouteInfo').length) { $('#newRouteInfo').hide(); } }"
            )
            self._stop.wait(0.7)
        except WebDriverException:
            if not quiet:
                raise

    def ajax(self, url: str, target: str, timeout: float = 20) -> WebElement:
        """Load a game fragment through the site's own Ajax() helper into #target and return that container.

        The container is emptied first so that the wait below sees the NEW content, never the old one.
        """
        self.js("var e = document.getElementById(arguments[1]); if (e) { e.innerHTML = ''; } Ajax(arguments[0], arguments[1]);",
                url, target)
        xpath = f"//*[@id='{target}']"
        wait = WebDriverWait(self.driver, timeout)
        wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        wait.until(lambda d: d.execute_script(_LOADED_JS, target))
        self._stop.wait(0.6)
        return self.driver.find_element(By.XPATH, xpath)

    def wait_loaded(self, target: str, timeout: float = 20, stale: Optional[WebElement] = None) -> str:
        """Wait for the game's answer in #target after a click and return its text ('' on timeout).

        *stale* is an element of the old content (usually the clicked button): the wait first lets it
        disappear, so the old content is never mistaken for the answer.
        """
        wait = WebDriverWait(self.driver, timeout)
        try:
            if stale is not None:
                wait.until(EC.staleness_of(stale))
            wait.until(lambda d: d.execute_script(_LOADED_JS, target))
        except TimeoutException:
            return ""
        self._stop.wait(0.5)
        text = self.js("var e = document.getElementById(arguments[0]); return e ? e.textContent : '';", target) or ""
        return " ".join(text.split())

    def wait_text(self, xpath: str, timeout: float = 10) -> str:
        """Wait until the element has some text (a server response) and return it."""
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: (d.find_element(By.XPATH, xpath).get_attribute("textContent") or "").strip()
            )
        except TimeoutException:
            return ""
        text = self.driver.find_element(By.XPATH, xpath).get_attribute("textContent") or ""
        return " ".join(text.split())

    def js(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def click_element(self, element: WebElement) -> None:
        try:
            element.click()
        except WebDriverException:  # hidden or overlapped element: click through JS
            self.js("arguments[0].click();", element)

    def pause(self, low: float = 0.6, high: float = 1.6) -> None:
        # Interruptible human-like pause: returns at once when the bot is being stopped.
        self._stop.wait(random.uniform(low, high))

    # ------------------------------------------------------------------ private helpers
    def _sel(self, name: str) -> str:
        xpath = self.config.get("selectors", name)
        if not xpath:
            raise KeyError(f"Falta el selector '{name}' en config/settings.ini")
        return xpath

    def _find(self, xpath: str, timeout: float = 10) -> Optional[WebElement]:
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
        except TimeoutException:
            return None

    def _text(self, xpath: str, timeout: float = 10) -> Optional[str]:
        element = self._find(xpath, timeout)
        return element.text.strip() if element is not None else None

    def _click(self, xpath: str, timeout: float = 10) -> None:
        element = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        self.pause()
        self.click_element(element)

    def _type(self, xpath: str, text: str, timeout: float = 10) -> None:
        element = WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )
        self.pause()
        element.clear()
        element.send_keys(text)

    def _quit_driver(self) -> None:
        driver, self.driver = self.driver, None
        if driver is None:
            return
        try:
            driver.quit()
        except WebDriverException:
            pass
