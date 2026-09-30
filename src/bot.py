"""Airline Manager 4 automation: log in, depart all aircraft, buy fuel / CO2 when cheap.

The bot runs in its own daemon thread. The GUI only reads ``state``, ``stats()``
and ``next_cycle_at``; it never touches the WebDriver.
"""
from __future__ import annotations

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

from config import AppConfig
from driver import create_driver

log = logging.getLogger("am4bot")

# Fuel and CO2 prices change every 30 minutes: buy at most once per price window.
PRICE_WINDOW_SECONDS = 1800

_HOLDING_RE = re.compile(r"holding\D{0,20}([\d.,]+)", re.I)
_CAPACITY_RE = re.compile(r"capacity\D{0,20}([\d.,]+)", re.I)
_PRICE_RE = re.compile(r"\$\s*([\d.,]+)")

# Recoverable Selenium errors: log them and carry on with the next cycle.
_SOFT_ERRORS = (TimeoutException, NoSuchElementException, StaleElementReferenceException, JavascriptException)


class BotState(str, Enum):
    IDLE = "Idle"
    STARTING = "Starting browser"
    LOGGING_IN = "Logging in"
    RUNNING = "Running"
    STOPPING = "Stopping"
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
    updated_at: Optional[float] = None


def to_int(text: Optional[str]) -> Optional[int]:
    """'$ 2,520,974' -> 2520974. None when there are no digits."""
    if text is None:
        return None
    digits = re.sub(r"\D", "", str(text))
    return int(digits) if digits else None


def _first_int(pattern: re.Pattern[str], text: str) -> Optional[int]:
    match = pattern.search(text or "")
    return to_int(match.group(1)) if match else None


def fmt(value: Optional[int]) -> str:
    return f"{value:,}" if isinstance(value, int) else "?"


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
        self._last_buy_window: dict[str, int] = {}

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self.last_error = None
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

    def stats(self) -> Stats:
        with self._stats_lock:
            return replace(self._stats)

    def _update_stats(self, **values: Optional[int]) -> None:
        with self._stats_lock:
            for key, value in values.items():
                if value is not None:
                    setattr(self._stats, key, value)
            self._stats.updated_at = time.time()

    # ------------------------------------------------------------------ main loop
    def _run(self) -> None:
        try:
            self.state = BotState.STARTING
            log.info("Starting Chrome ...")
            self.driver = create_driver(
                url=self.config.get("app", "url", "https://www.airlinemanager.com/"),
                keep_session=self.config.get_bool("options", "keep_session"),
                headless=self.config.get_bool("options", "headless"),
            )
            self.state = BotState.LOGGING_IN
            if not self._login():
                raise RuntimeError("Login failed or timed out")
            self.state = BotState.RUNNING
            while not self._stop.is_set():
                self._cycle()
                if self._stop.is_set():
                    break
                self._sleep_until_next_cycle()
        except Exception as exc:  # noqa: BLE001 - every failure must reach the GUI log
            if self._stop.is_set():
                log.info("Bot stopped.")
            else:
                self.state = BotState.ERROR
                self.last_error = (str(exc).splitlines() or [exc.__class__.__name__])[0]
                log.error("Bot stopped with an error: %s", self.last_error)
                log.debug("Traceback:", exc_info=True)
        else:
            log.info("Bot stopped.")
        finally:
            self._quit_driver()
            self.next_cycle_at = None
            if self.state is not BotState.ERROR:
                self.state = BotState.IDLE

    def _cycle(self) -> None:
        self._ensure_session()
        log.info("Checking airline ...")
        self._guard(self._read_header, "reading money and points")
        if self.config.get_bool("options", "auto_depart"):
            self._guard(self._depart_all, "departing aircraft")
        if self.config.get_bool("options", "autobuy_fuel") or self.config.get_bool("options", "autobuy_co2"):
            self._guard(self._check_market, "checking the fuel / CO2 market")

    def _guard(self, action: Callable[[], None], what: str) -> None:
        try:
            action()
        except _SOFT_ERRORS as exc:
            log.warning("Problem while %s: %s. Skipping until next cycle.", what, exc.__class__.__name__)
            log.debug("Details:", exc_info=True)
            self._close_popup(quiet=True)

    def _sleep_until_next_cycle(self) -> None:
        low = max(1, self.config.get_int("settings", "cycle_min_minutes", 5))
        high = max(low, self.config.get_int("settings", "cycle_max_minutes", 10))
        seconds = random.uniform(low * 60, high * 60)
        self.next_cycle_at = time.time() + seconds
        log.info("Next check in %d min %02d s.", seconds // 60, seconds % 60)
        self._wake.wait(seconds)
        self._wake.clear()
        self.next_cycle_at = None

    def _ensure_session(self) -> None:
        # Raises WebDriverException (fatal) when the user closed the browser.
        self.driver.current_url
        if self._is_logged_in(timeout=5):
            return
        log.warning("Session lost, logging in again ...")
        self.state = BotState.LOGGING_IN
        self.driver.get(self.config.get("app", "url", "https://www.airlinemanager.com/"))
        if not self._login():
            raise RuntimeError("Could not log in again")
        self.state = BotState.RUNNING

    # ------------------------------------------------------------------ login
    def _login(self) -> bool:
        if self._is_logged_in(timeout=5):
            log.info("Already logged in (session restored).")
            return True

        username, password = self.config.credentials
        timeout = max(30, self.config.get_int("settings", "login_timeout", 300))

        if username and password:
            log.info("Logging in as %s ...", username)
            self._open_login_form()
            self._type(self._sel("login_email"), username)
            self._type(self._sel("login_password"), password)
            remember = self._find(self._sel("login_remember"), timeout=5)
            if remember is not None and not remember.is_selected():
                self._human_pause()
                remember.click()
            self._click(self._sel("login_submit"))
        else:
            log.warning("No credentials given: log in by hand in the Chrome window.")

        started = time.time()
        warned = False
        while not self._stop.is_set() and time.time() - started < timeout:
            if self._is_logged_in(timeout=3):
                log.info("Logged in.")
                return True
            if not warned and time.time() - started > 20:
                log.warning(
                    "Not logged in yet. If the site shows a captcha or an error, finish the login by hand "
                    "(waiting up to %d s).",
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
            self._js("login('show');")
        except JavascriptException:
            self._click("//button[contains(@onclick, \"signup('show')\")]")
            self._click("//button[contains(@onclick, \"login('show')\")]")
        WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, self._sel("login_email")))
        )

    # ------------------------------------------------------------------ actions
    def _read_header(self) -> None:
        money = to_int(self._text(self._sel("money"), timeout=5))
        points = to_int(self._text(self._sel("points"), timeout=3))
        self._update_stats(money=money, points=points)
        log.info("Money: $%s | Points: %s", fmt(money), fmt(points))

    def _depart_all(self) -> None:
        self._open_popup("routes_main.php", "Routes", "nav_routes")
        button = self._find(self._sel("depart_all"), timeout=5)
        if button is None:
            log.info("No aircraft ready to depart.")
        elif not button.is_displayed() or not button.is_enabled() or "not-active" in (button.get_attribute("class") or ""):
            log.info("'Depart all' is disabled right now.")
        else:
            self._human_pause()
            button.click()
            log.info("Departed all aircraft.")
            self._stop.wait(2)
        self._close_popup()

    def _check_market(self) -> None:
        self._open_popup("fuel.php", "Fuel", "nav_fuel")
        if self.config.get_bool("options", "autobuy_fuel"):
            self._trade("fuel")
        if self.config.get_bool("options", "autobuy_co2"):
            self._click(self._sel("co2_tab"))
            WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.XPATH, self._sel("co2_main")))
            )
            self._trade("co2")
        self._close_popup()

    def _trade(self, kind: str) -> None:
        label = "CO2" if kind == "co2" else "Fuel"
        panel = self._find(self._sel(f"{kind}_main"), timeout=10)
        if panel is None:
            log.warning("%s panel not found.", label)
            return
        panel_text = panel.text

        price = to_int(self._text(self._sel(f"{kind}_price"), timeout=5))
        if price is None:
            price = _first_int(_PRICE_RE, panel_text)
        holding = _first_int(_HOLDING_RE, panel_text)
        capacity = _first_int(_CAPACITY_RE, panel_text)
        self._update_stats(**{f"{kind}_price": price, kind: holding, f"{kind}_capacity": capacity})

        if price is None:
            log.warning("Could not read the %s price.", label)
            return

        good_price = self.config.get_int("settings", f"{kind}_price_good")
        quantity = self.config.get_int("settings", f"{kind}_quantity_buy")
        storage = f" | holding {fmt(holding)} / {fmt(capacity)}" if holding is not None and capacity is not None else ""
        log.info("%s price: $%s (buying at <= $%s)%s", label, fmt(price), fmt(good_price), storage)

        if price > good_price or quantity <= 0:
            return
        window = int(time.time() // PRICE_WINDOW_SECONDS)
        if self._last_buy_window.get(kind) == window:
            log.info("%s already bought in this price window.", label)
            return
        if holding is not None and capacity is not None:
            quantity = min(quantity, capacity - holding)
            if quantity <= 0:
                log.info("%s storage is full, nothing to buy.", label)
                return
        money = self.stats().money
        if money is not None:
            affordable = int(money * 1000 // price)  # prices are per 1,000 units
            if affordable <= 0:
                log.info("Not enough money to buy %s.", label)
                return
            quantity = min(quantity, affordable)

        amount = WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, self._sel(f"{kind}_amount")))
        )
        self._human_pause()
        amount.clear()
        amount.send_keys(str(quantity))
        self._click(self._sel(f"{kind}_buy"))
        self._last_buy_window[kind] = window
        log.info("Bought %s %s at $%s (about $%s).", fmt(quantity), label, fmt(price), fmt(price * quantity // 1000))
        self._stop.wait(1.5)

    # ------------------------------------------------------------------ popups
    def _open_popup(self, url: str, title: str, nav_selector: str) -> None:
        nav_xpath = self.config.get("selectors", nav_selector)
        button = self._find(nav_xpath, timeout=3) if nav_xpath else None
        if button is not None:
            self._human_pause()
            try:
                button.click()
            except WebDriverException:
                self._js("arguments[0].click();", button)
        else:
            log.debug("Nav element '%s' not found, opening %s through the site's popup() helper.", nav_selector, url)
            self._js("popup(arguments[0], arguments[1], false, true);", url, title)

        content = self._sel("popup_content")
        wait = WebDriverWait(self.driver, 20)
        wait.until(EC.visibility_of_element_located((By.XPATH, content)))
        wait.until(lambda d: not d.find_elements(By.XPATH, content + "//img[contains(@src, 'loader')]"))
        self._stop.wait(0.5)

    def _close_popup(self, quiet: bool = False) -> None:
        try:
            self._js("if (window.jQuery && $('#popup').length) { $('#popup').modal('hide'); }")
            self._stop.wait(0.7)
        except WebDriverException:
            if not quiet:
                raise

    # ------------------------------------------------------------------ helpers
    def _sel(self, name: str) -> str:
        xpath = self.config.get("selectors", name)
        if not xpath:
            raise KeyError(f"Missing selector '{name}' in config/settings.ini")
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
        self._human_pause()
        try:
            element.click()
        except WebDriverException:  # something overlaps the element: click through JS
            self._js("arguments[0].click();", element)

    def _type(self, xpath: str, text: str, timeout: float = 10) -> None:
        element = WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((By.XPATH, xpath))
        )
        self._human_pause()
        element.clear()
        element.send_keys(text)

    def _js(self, script: str, *args):
        return self.driver.execute_script(script, *args)

    def _human_pause(self, low: float = 0.6, high: float = 1.6) -> None:
        # Interruptible sleep: returns at once when the bot is being stopped.
        self._stop.wait(random.uniform(low, high))

    def _quit_driver(self) -> None:
        driver, self.driver = self.driver, None
        if driver is None:
            return
        try:
            driver.quit()
        except WebDriverException:
            pass
