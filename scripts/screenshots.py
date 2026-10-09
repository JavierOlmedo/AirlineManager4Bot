"""Regenerate every screenshot in screenshots/ (desktop window and web dashboard, each tab, dark and light).

    .venv\\Scripts\\python.exe scripts\\screenshots.py

Safe to run while the bot is running: it never starts a bot, never saves settings.ini, logs into a
temporary file and uses its own web port. It shows sample statistics (realistic values) and an example
account, so no e-mail, chat id or other personal data ends up in the images. The desktop part needs
Windows (it captures the window by its handle); the web part needs Google Chrome.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "screenshots"
WEB_PORT = 8799
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402

# --- configuration patches: no bot, no saving, no personal data -------------------------------------
_get, _get_bool, _get_int = config.AppConfig.get, config.AppConfig.get_bool, config.AppConfig.get_int
LOG_FILE = Path(tempfile.gettempdir()) / "am4bot-screenshots.log"
APPEARANCE = {"mode": "Dark"}


def _patched_get(self, section, key, fallback=""):
    if (section, key) == ("app", "log_file"):
        return str(LOG_FILE)
    if (section, key) == ("app", "appearance_mode"):
        return APPEARANCE["mode"]
    return _get(self, section, key, fallback)


def _patched_get_bool(self, section, key, fallback=False):
    if (section, key) == ("web", "enabled"):
        return False
    return _get_bool(self, section, key, fallback)


config.AppConfig.get = _patched_get
config.AppConfig.get_bool = _patched_get_bool
config.AppConfig.get_int = lambda self, s, k, fallback=0: WEB_PORT if (s, k) == ("web", "port") else _get_int(self, s, k, fallback)
config.AppConfig.save = lambda self: None
config.AppConfig.credentials = property(lambda self: ("piloto@ejemplo.com", "contraseña-de-ejemplo"))
config.AppConfig.telegram = property(lambda self: ("123456789:EXAMPLE", "123456789"))
config.AppConfig.web_token = property(lambda self: "")

SAMPLE_STATS = dict(money=1925006, points=134, fuel=7382536, fuel_capacity=8000000, fuel_price=1200, fuel_buy_at=600,
                    co2=2745179, co2_capacity=4000000, co2_price=125, co2_buy_at=120, fleet_size=21, inflight=13,
                    parked=0, pending=2, income_day=9436178, goal_price=6800000, hangar_free=2, hangar_capacity=23,
                    reputation=87)
SAMPLE_LOG = [
    ("bot", "Revisando la aerolínea ..."),
    ("dinero", "Dinero: $1,925,006 | Puntos: 134 | ingresos netos ~$9,436,178/día"),
    ("vuelos", "13 aviones en vuelo, próximo aterrizaje en 04:12."),
    ("marketing", "Reputación 87 % | 2 campañas activas, la primera acaba en 6:57 h."),
    ("mant", "Flota: 21 aviones | mayor desgaste 44.9% (EC-006) | próximo A-check en 130 h (FIRST)"),
    ("asientos", "Asientos cambiados: First (B737-800, EPRZ - LEMD): Y184 J0 F0 -> Y106 J27 F8, +$979k/día estimado, "
                 "coste $344,000, 2.5 h en el taller, se paga en 0.4 días."),
    ("vuelos", "Todos los aviones han despegado."),
    ("fuel", "Precio fuel: $410 (compro a <= $600) | tanque 6,658,790 / 8,000,000 | histórico 3d: mín 310, p10 520"),
    ("fuel", "Comprado: 715,056 fuel a $410 (unos $293,172, precio excepcional)."),
    ("co2", "Precio CO2: $125 (compro a <= $120) | tanque 2,745,179 / 4,000,000"),
    ("flota", "0 aviones aparcados sin ruta, 2 pendientes de entrega."),
    ("aviones", "Escalera: siguiente avión DC-10-10 ($6.8M, 250 plazas, gana ~$2.4M/día, se paga en ~2.9 días)."),
    ("checklist", "✅ Checklist: tarea completada «Fly with your first 1st class passenger»."),
    ("bot", "Próxima revisión en 4 min 31 s (me adelanto por el próximo aterrizaje)."),
]


def fill(bot) -> None:
    bot.update_stats(**SAMPLE_STATS, campaign_ends=int(time.time()) + 6 * 3600 + 57 * 60)
    for name, message in SAMPLE_LOG:
        logging.getLogger(f"am4bot.{name}").info(message)


# --- desktop window ----------------------------------------------------------------------------------
def capture_window(app, path: Path) -> None:
    import ctypes
    from ctypes import wintypes

    from PIL import ImageGrab

    app.attributes("-topmost", True)
    app.lift()
    app.update()
    time.sleep(0.6)
    app.update()
    hwnd = ctypes.windll.user32.GetParent(app.winfo_id()) or app.winfo_id()
    rect = wintypes.RECT()
    # the visible frame, without the invisible resize border of Windows 10/11
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
    image.save(path, optimize=True)
    print("saved", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path, image.size)


def desktop_shots() -> None:
    if os.name != "nt":
        print("desktop screenshots need Windows, skipped")
        return
    from app import App, tab_title

    App.start_bot = lambda self: None  # "Iniciar el bot al abrir" keeps its real value but never starts anything
    for mode, tabs in (("Dark", ("Mercado", "Flota", "Aviones", "Opciones")), ("Light", ("Mercado",))):
        APPEARANCE["mode"] = mode
        app = App()
        app.title("Airline Manager 4 Bot")
        app.geometry("1280x880+40+20")
        fill(app.bot)
        for _ in range(6):  # let the log queue and the tiles refresh
            app.update()
            time.sleep(0.3)
        app._refresh_goal_panel()
        for tab in tabs:
            app.tabs.set(tab_title(tab))
            name = f"desktop-{tab.lower()}" + ("-light" if mode == "Light" else "")
            capture_window(app, OUT / f"{name}.png")
        app.destroy()


# --- web dashboard -----------------------------------------------------------------------------------
def web_shots() -> None:
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    from bot import Bot
    from logsetup import LogBuffer, setup_logging
    from web import WebDashboard

    cfg = config.AppConfig()
    buffer = LogBuffer()
    setup_logging(cfg, buffer)
    bot = Bot(cfg)
    bot.start = lambda: None
    web = WebDashboard(bot, cfg, buffer)
    if not web.start():
        print("web dashboard could not start, skipped")
        return
    # a fresh log without the "Panel web en ...:8799" line of this temporary server
    web.buffer = LogBuffer()
    setup_logging(cfg, web.buffer)
    fill(bot)
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--hide-scrollbars")
    driver = webdriver.Chrome(options=options)
    try:
        def shot(name: str, width: int, height: int, light: bool = False, tab: int = 0) -> None:
            driver.set_window_size(width, height)
            driver.execute_cdp_cmd("Emulation.setEmulatedMedia",
                                   {"features": [{"name": "prefers-color-scheme", "value": "light" if light else "dark"}]})
            driver.get(f"http://127.0.0.1:{WEB_PORT}/")
            time.sleep(2.5)
            if tab:
                driver.find_elements(By.CSS_SELECTOR, "#tabs button")[tab].click()
                time.sleep(0.5)
            driver.save_screenshot(str(OUT / name))
            print("saved", f"screenshots/{name}")

        for index, tab in enumerate(("mercado", "flota", "aviones", "opciones")):
            shot(f"web-{tab}.png", 1400, 900, tab=index)
        shot("web-mercado-light.png", 1400, 900, light=True)
        shot("web-mobile.png", 430, 1500)
    finally:
        driver.quit()
        web.stop()


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    desktop_shots()
    web_shots()
