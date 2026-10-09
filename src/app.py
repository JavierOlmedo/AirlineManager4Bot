"""customtkinter GUI for Airline Manager 4 Bot (user-facing text in Spanish).

Layout: a sidebar (account, start / stop, status), a strip of statistic tiles, the settings tabs at full
width and the log, always visible, below. The same data, controls and settings are also served as a web
dashboard (web.py) while the window is open.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from PIL import Image

from bot import Bot, BotState
from config import AppConfig
from dashboard import fmt_clock, goal_status, ladder_step, last_money, snapshot
import paths
from economy import (AUTO_GOAL_LABEL, find_model, fmt_days, fmt_money, income_per_day, is_auto_goal, load_market,
                     load_state, market_file, state_file)
from i18n import LANGUAGES, language, set_language, t, tip
from helpers import LEVEL_STYLES, LOG_TAGS, fmt, log_tag
from logsetup import LogBuffer, setup_logging
from market import PriceHistory, history_file
from notify import Telegram
from settings_schema import (AIRCRAFT_FIELDS, AIRCRAFT_SWITCHES, ALL_FIELDS, FLEET_FIELDS, FLEET_SWITCHES,
                             MARKET_FIELDS, MARKET_SWITCHES, MARKETING_FIELDS, OPTION_DEFAULTS, OPTION_SWITCHES, TABS,
                             clamp_settings, parse_int)
from supervisor import AutoRestart
from shortcuts import create_desktop_shortcut, launch
from web import WebDashboard, profile_running, profile_token, running_instance
from widgets import ToolTip, add_tooltip

log = logging.getLogger("am4bot.app")

MAX_LOG_LINES = 800
WINDOW_SIZE = (1280, 880)
THEME_FILE = Path("assets/theme.json")

# Palette shared with assets/theme.json: (light, dark)
MUTED = ("#656d76", "#8b949e")
BORDER = ("#d0d7de", "#30363d")
PILL_COLORS = {
    BotState.IDLE: ("#8c959f", "#484f58"),
    BotState.STARTING: ("#bf8700", "#9e6a03"),
    BotState.LOGGING_IN: ("#bf8700", "#9e6a03"),
    BotState.RUNNING: ("#1f883d", "#238636"),
    BotState.STOPPING: ("#bf8700", "#9e6a03"),
    BotState.ERROR: ("#cf222e", "#da3633"),
}
GREEN = (("#1f883d", "#238636"), ("#1a7f37", "#2ea043"))
RED = (("#cf222e", "#da3633"), ("#a40e26", "#b62324"))

# customtkinter needs the English appearance names; the menu shows them in the interface language.
THEME_NAMES = {"Light": "Claro", "Dark": "Oscuro", "System": "Sistema"}
PROFILE_NEW = "➕ Nuevo perfil…"


def theme_labels() -> dict[str, str]:
    """customtkinter appearance name -> its label in the interface language."""
    return {mode: t(label) for mode, label in THEME_NAMES.items()}


# Statistic tiles: (key for the help text, title, has a progress bar)
TILES = [
    ("money", "💰  DINERO", False),
    ("reputation", "⭐  REPUTACIÓN", True),
    ("fuel", "⛽  FUEL", True),
    ("co2", "🌿  CO2", True),
    ("fleet", "🛩  FLOTA", False),
    ("goal", "🎯  OBJETIVO", True),
]
# Tk draws the emoji variation selector (U+FE0F) as a gap, so the window uses the plain symbols.
TAB_ICONS = {name: icon.replace(chr(0xFE0F), "") for name, icon, _fields, _switches in TABS}


def tab_title(name: str) -> str:
    return f"{TAB_ICONS[name]}  {t(name)}"

# Well-known big aircraft always shown in the goal suggestions when they exist in the market.
ICONIC_GOALS = ("A330-300", "B777-300ER", "B747-400", "A380-800")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig()
        set_language(self.cfg.get("app", "language", "es"))
        self.bot = Bot(self.cfg)
        self.log_queue: "queue.Queue[logging.LogRecord]" = queue.Queue()
        self.log_buffer = LogBuffer()
        self.log_file = setup_logging(self.cfg, logging.handlers.QueueHandler(self.log_queue), self.log_buffer)
        self.restart = AutoRestart()
        self._actions: "queue.Queue[str]" = queue.Queue()   # requests from the web thread, run on the Tk thread
        self._ui_error_at = 0.0

        ctk.set_appearance_mode(self.cfg.get("app", "appearance_mode", "System"))
        theme = self.cfg.get("app", "color_theme", "am4")
        ctk.set_default_color_theme(str(THEME_FILE) if theme == "am4" and THEME_FILE.exists() else theme)

        title = self.cfg.get("app", "title", "Airline Manager 4 Bot")
        self.title(title if self.cfg.profile.is_main else f"{title} · {self.cfg.profile.label}")
        self._set_icon()
        self.minsize(1100, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        family = "Segoe UI" if platform.system() == "Windows" else None
        font = (lambda **kw: ctk.CTkFont(family=family, **kw)) if family else (lambda **kw: ctk.CTkFont(**kw))
        self.font = font(size=13)
        self.font_bold = font(size=13, weight="bold")
        self.font_title = font(size=15, weight="bold")
        self.font_small = font(size=11)
        self.font_caption = font(size=11, weight="bold")
        self.font_value = font(size=21, weight="bold")
        mono = {"Windows": "Consolas", "Darwin": "Menlo"}.get(platform.system(), "DejaVu Sans Mono")
        self.font_mono = ctk.CTkFont(family=mono, size=12)

        self.setting_entries: dict[str, ctk.CTkEntry] = {}
        self.option_vars: dict[str, tk.BooleanVar] = {}
        # cached files for the goal panel and the price hints
        self._history = PriceHistory()
        self._state: dict = load_state()
        self._market: list[dict] = load_market()
        self._mtimes: dict[str, float] = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_sidebar()
        self._build_tiles()
        self._build_tabs()
        self._build_logs()
        self._center()
        self._cfg_seen = self.cfg.version

        log.info("Interfaz cargada.")
        self.web: Optional[WebDashboard] = None
        if self.cfg.get_bool("web", "enabled", True):
            self.web = WebDashboard(self.bot, self.cfg, self.log_buffer, lambda: self.restart.restart_in,
                                    start_bot=lambda: self._actions.put("start"), on_quit=lambda: self._actions.put("quit"))
            if self.web.start():
                self._show_web_link()
        self.after(300, self._poll)
        self.after(800, self._refresh_files)
        if self.cfg.get_bool("options", "start_on_launch"):
            self.after(600, self.start_bot)

    # ------------------------------------------------------------------ setup
    def _set_icon(self) -> None:
        try:
            if platform.system() == "Windows":
                self.iconbitmap("assets/favicon.ico")
            else:
                self.iconphoto(True, tk.PhotoImage(file="assets/logo.png"))
        except Exception:  # noqa: BLE001 - purely cosmetic
            pass

    def _center(self) -> None:
        width, height = WINDOW_SIZE
        self.update_idletasks()
        width = min(width, self.winfo_screenwidth() - 40)
        height = min(height, self.winfo_screenheight() - 80)
        x = (self.winfo_screenwidth() - width) // 2
        y = max((self.winfo_screenheight() - height) // 2 - 30, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------ small builders
    def _int_field(self, parent: ctk.CTkFrame, row: int, key: str, text: str) -> None:
        label = ctk.CTkLabel(parent, text=t(text), font=self.font, anchor="w")
        label.grid(row=row, column=0, sticky="w", pady=2)
        entry = ctk.CTkEntry(parent, width=92, height=28, font=self.font_bold, justify="right")
        entry.insert(0, str(self.cfg.get_int("settings", key)))
        entry.grid(row=row, column=1, sticky="e", pady=2, padx=(8, 0))
        self.setting_entries[key] = entry
        add_tooltip(label, tip(key))
        add_tooltip(entry, tip(key))

    def _switch(self, parent: ctk.CTkFrame, row: int, key: str, text: str) -> None:
        var = tk.BooleanVar(value=self.cfg.get_bool("options", key, OPTION_DEFAULTS.get(key, False)))
        switch = ctk.CTkSwitch(parent, text=t(text), variable=var, onvalue=True, offvalue=False, font=self.font,
                               switch_width=38, switch_height=20, command=lambda k=key: self._on_option(k))
        switch.grid(row=row, column=0, sticky="w", pady=3)
        self.option_vars[key] = var
        add_tooltip(switch, tip(key))

    def _save_button(self, parent, width: int = 150, **grid) -> None:
        button = ctk.CTkButton(parent, text=t("Guardar ajustes"), font=self.font_bold, height=30, width=width,
                               command=self._save_settings)
        button.grid(**grid)
        add_tooltip(button, tip("save"))

    def _columns(self, parent: ctk.CTkFrame, items: list[tuple[str, str]], columns: int, builder, row: int = 0) -> None:
        """Lay *items* out in *columns* equal columns at grid *row* of *parent* using *builder(frame, row, key, text)*."""
        per_column = (len(items) + columns - 1) // columns
        for column in range(columns):
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            frame.grid(row=row, column=column, sticky="new", padx=(0 if column == 0 else 28, 0))
            frame.grid_columnconfigure(0, weight=1)
            parent.grid_columnconfigure(column, weight=1, uniform=f"cols{row}")
            for index, (key, text) in enumerate(items[column * per_column:(column + 1) * per_column]):
                builder(frame, index, key, text)

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=244, corner_radius=0, border_width=0)
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(12, weight=1)

        top = ctk.CTkFrame(sidebar, fg_color="transparent")
        top.grid(row=0, column=0, padx=20, pady=(26, 16), sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        banner = ctk.CTkImage(Image.open("assets/banner.png"), size=(196, 46))
        ctk.CTkLabel(top, text="", image=banner).grid(row=0, column=0, pady=(0, 16))
        profile_caption = ctk.CTkLabel(top, text=t("PERFIL"), font=self.font_caption, text_color=MUTED, anchor="w")
        profile_caption.grid(row=1, column=0, padx=2, sticky="ew")
        self.profile_menu = ctk.CTkOptionMenu(top, values=self._profile_values(), command=self._on_profile, font=self.font_bold)
        self.profile_menu.set(self.cfg.profile.label)
        self.profile_menu.grid(row=2, column=0, pady=(6, 0), sticky="ew")
        self.mode_label = ctk.CTkLabel(top, text="", font=self.font_small, text_color=MUTED, anchor="w", height=16)
        self.mode_label.grid(row=3, column=0, padx=2, pady=(4, 0), sticky="ew")
        add_tooltip(self.mode_label, tip("game_mode"))
        add_tooltip(profile_caption, tip("profile"))
        add_tooltip(self.profile_menu, tip("profile"))

        account = ctk.CTkLabel(sidebar, text=t("CUENTA"), font=self.font_caption, text_color=MUTED, anchor="w")
        account.grid(row=1, column=0, padx=22, sticky="ew")
        add_tooltip(account, tip("account"))
        username, password = self.cfg.credentials
        self.entry_user = ctk.CTkEntry(sidebar, placeholder_text=t("Correo"), font=self.font, height=34)
        self.entry_user.grid(row=2, column=0, padx=20, pady=(6, 6), sticky="ew")
        self.entry_pass = ctk.CTkEntry(sidebar, placeholder_text=t("Contraseña"), show="•", font=self.font, height=34)
        self.entry_pass.grid(row=3, column=0, padx=20, sticky="ew")
        # Inserting an empty string would hide the placeholder text.
        if username:
            self.entry_user.insert(0, username)
        if password:
            self.entry_pass.insert(0, password)
        add_tooltip(self.entry_user, tip("account"))
        add_tooltip(self.entry_pass, tip("account"))

        self.var_remember = tk.BooleanVar(value=self.cfg.get_bool("options", "remember_credentials", True))
        remember = ctk.CTkCheckBox(
            sidebar, text=t("Recordar credenciales"), variable=self.var_remember, font=self.font_small,
            checkbox_width=18, checkbox_height=18, command=self._on_remember_toggle,
        )
        remember.grid(row=4, column=0, padx=22, pady=(10, 18), sticky="w")
        add_tooltip(remember, tip("remember"))

        self.btn_start = ctk.CTkButton(sidebar, text=t("▶  INICIAR BOT"), font=self.font_bold, height=40,
                                       fg_color=GREEN[0], hover_color=GREEN[1], command=self.start_bot)
        self.btn_start.grid(row=5, column=0, padx=20, sticky="ew")
        self.btn_stop = ctk.CTkButton(sidebar, text=t("■  PARAR BOT"), font=self.font_bold, height=40,
                                      fg_color=RED[0], hover_color=RED[1], state="disabled", command=self.stop_bot)
        self.btn_stop.grid(row=6, column=0, padx=20, pady=(8, 0), sticky="ew")
        self.btn_run_now = ctk.CTkButton(
            sidebar, text=t("⟳  Ejecutar ciclo ahora"), font=self.font, height=32, fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=("#1f2328", "#e6edf3"), hover_color=("#eaeef2", "#21262d"),
            state="disabled", command=self.bot.run_now,
        )
        self.btn_run_now.grid(row=7, column=0, padx=20, pady=(8, 0), sticky="ew")
        add_tooltip(self.btn_start, tip("btn_start"))
        add_tooltip(self.btn_stop, tip("btn_stop"))
        add_tooltip(self.btn_run_now, tip("btn_run_now"))

        ctk.CTkLabel(sidebar, text=t("ESTADO"), font=self.font_caption, text_color=MUTED, anchor="w").grid(
            row=8, column=0, padx=22, pady=(24, 4), sticky="ew")
        self.status_pill = ctk.CTkLabel(sidebar, text=f"●  {t('Parado').upper()}", font=self.font_bold, height=30, corner_radius=15,
                                        fg_color=PILL_COLORS[BotState.IDLE], text_color="#ffffff")
        self.status_pill.grid(row=9, column=0, padx=20, sticky="w")
        add_tooltip(self.status_pill, tip("status"))
        self.next_label = ctk.CTkLabel(sidebar, text="", font=self.font_small, text_color=MUTED, anchor="w",
                                       justify="left", wraplength=200)
        self.next_label.grid(row=10, column=0, padx=22, pady=(6, 0), sticky="ew")
        self.web_label = ctk.CTkLabel(sidebar, text="", font=self.font_small, text_color=("#0969da", "#58a6ff"),
                                      anchor="w", cursor="hand2")
        self.web_label.grid(row=11, column=0, padx=22, pady=(10, 0), sticky="ew")
        self.web_label.bind("<Button-1>", lambda _event: self.open_web())
        self.web_label.tooltip = ToolTip(self.web_label, "")

        ctk.CTkLabel(sidebar, text=t("APARIENCIA"), font=self.font_caption, text_color=MUTED, anchor="w").grid(
            row=13, column=0, padx=22, sticky="ew"
        )
        self.theme_menu = ctk.CTkOptionMenu(sidebar, values=list(theme_labels().values()), command=self.change_theme,
                                            font=self.font)
        self.theme_menu.set(theme_labels().get(self.cfg.get("app", "appearance_mode", "System"), t("Sistema")))
        self.theme_menu.grid(row=14, column=0, padx=20, pady=(6, 12), sticky="ew")
        add_tooltip(self.theme_menu, tip("theme"))
        language_caption = ctk.CTkLabel(sidebar, text=t("IDIOMA"), font=self.font_caption, text_color=MUTED, anchor="w")
        language_caption.grid(row=15, column=0, padx=22, sticky="ew")
        # Each language is shown in its own name, so it can always be found
        self.language_menu = ctk.CTkOptionMenu(sidebar, values=list(LANGUAGES.values()), command=self.change_language,
                                               font=self.font)
        self.language_menu.set(LANGUAGES[language()])
        self.language_menu.grid(row=16, column=0, padx=20, pady=(6, 20), sticky="ew")
        add_tooltip(language_caption, tip("language"))
        add_tooltip(self.language_menu, tip("language"))

    # ------------------------------------------------------------------ statistic tiles
    def _build_tiles(self) -> None:
        strip = ctk.CTkFrame(self, fg_color="transparent")
        strip.grid(row=0, column=1, sticky="ew", padx=16, pady=(16, 10))
        self.tiles: dict[str, tuple[ctk.CTkLabel, ctk.CTkLabel, Optional[ctk.CTkProgressBar]]] = {}
        for column, (key, title, has_bar) in enumerate(TILES):
            strip.grid_columnconfigure(column, weight=1, uniform="tiles")
            tile = ctk.CTkFrame(strip, border_width=1, border_color=BORDER)
            tile.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 10, 0))
            tile.grid_columnconfigure(0, weight=1)
            head = ctk.CTkLabel(tile, text=t(title), font=self.font_caption, text_color=MUTED, anchor="w")
            head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
            value = ctk.CTkLabel(tile, text="-", font=self.font_value, anchor="w")
            value.grid(row=1, column=0, sticky="ew", padx=14)
            sub = ctk.CTkLabel(tile, text="", font=self.font_small, text_color=MUTED, anchor="w", justify="left",
                               wraplength=150)
            sub.grid(row=2, column=0, sticky="ew", padx=14)
            bar = None
            if has_bar:
                bar = ctk.CTkProgressBar(tile, height=6)
                bar.set(0)
                bar.grid(row=3, column=0, sticky="ew", padx=14, pady=(6, 12))
            else:
                ctk.CTkLabel(tile, text="", height=6).grid(row=3, column=0, pady=(6, 12))
            tile.bind("<Configure>", lambda e, label=sub: label.configure(wraplength=max(100, e.width - 30)))
            for widget in (tile, head, value, sub):
                add_tooltip(widget, tip(key))
            self.tiles[key] = (value, sub, bar)

    # ------------------------------------------------------------------ settings tabs
    def _build_tabs(self) -> None:
        self.tabs = tabs = ctk.CTkTabview(self, border_width=1, border_color=BORDER, height=262)
        tabs.grid(row=1, column=1, sticky="nsew", padx=16, pady=(0, 10))
        for name, _icon, _fields, _switches in TABS:
            tabs.add(tab_title(name))
        tab = lambda name: tabs.tab(tab_title(name))  # noqa: E731

        # --- Mercado: price rules in two columns, the lowest price ever seen next to the price boxes
        market = tab("Mercado")
        self._columns(market, MARKET_FIELDS, 2, self._int_field)
        self.record_labels: dict[str, ctk.CTkLabel] = {}
        for kind in ("fuel", "co2"):
            entry = self.setting_entries[f"{kind}_price_good"]
            hint = ctk.CTkLabel(entry.master, text="", font=self.font_small, text_color=MUTED, anchor="w", width=10)
            hint.grid(row=entry.grid_info()["row"], column=2, sticky="w", padx=(8, 0))
            hint.tooltip = ToolTip(hint, "")
            self.record_labels[kind] = hint
        bottom = ctk.CTkFrame(market, fg_color="transparent")
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        for row, (key, text) in enumerate(MARKET_SWITCHES):
            self._switch(bottom, row, key, text)
        self._save_button(bottom, row=0, column=1, sticky="e")

        # --- Flota: switches on the left, numbers in two columns on the right
        fleet = tab("Flota")
        fleet.grid_columnconfigure(1, weight=1)
        switches = ctk.CTkFrame(fleet, fg_color="transparent")
        switches.grid(row=0, column=0, sticky="nw", padx=(0, 32))
        for row, (key, text) in enumerate(FLEET_SWITCHES):
            self._switch(switches, row, key, text)
        self._save_button(switches, row=len(FLEET_SWITCHES), column=0, sticky="w", pady=(10, 0))
        fields = ctk.CTkFrame(fleet, fg_color="transparent")
        fields.grid(row=0, column=1, sticky="new")
        self._columns(fields, FLEET_FIELDS, 2, self._int_field)

        # --- Aviones: purchases and the savings goal
        aircraft = tab("Aviones")
        aircraft.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(aircraft, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nw", padx=(0, 24))
        for row, (key, text) in enumerate(AIRCRAFT_SWITCHES):
            self._switch(left, row, key, text)
        form = ctk.CTkFrame(left, fg_color="transparent")
        form.grid(row=len(AIRCRAFT_SWITCHES), column=0, sticky="ew", pady=(6, 0))
        form.grid_columnconfigure(0, weight=1)
        goal_label = ctk.CTkLabel(form, text=t("Avión objetivo"), font=self.font, anchor="w")
        goal_label.grid(row=0, column=0, sticky="w", pady=2)
        self.goal_combo = ctk.CTkComboBox(form, width=180, height=28, font=self.font_bold, values=self._goal_values(),
                                          command=lambda _value: self._refresh_goal_panel())
        saved_goal = self.cfg.get("settings", "goal_model")
        self.goal_combo.set(t(AUTO_GOAL_LABEL) if is_auto_goal(saved_goal) else saved_goal)
        self.goal_combo.grid(row=0, column=1, sticky="e", pady=2, padx=(8, 0))
        self.goal_combo.bind("<KeyRelease>", lambda _e: self._refresh_goal_panel())
        add_tooltip(goal_label, tip("goal_model"))
        model_label = ctk.CTkLabel(form, text=t("Modelo fijo sin objetivo"), font=self.font, anchor="w")
        model_label.grid(row=1, column=0, sticky="w", pady=2)
        self.entry_model = ctk.CTkEntry(form, width=180, height=28, font=self.font_bold, placeholder_text=t("vacío = más rentable"))
        model = self.cfg.get("settings", "aircraft_model")
        if model:
            self.entry_model.insert(0, model)
        self.entry_model.grid(row=1, column=1, sticky="e", pady=2, padx=(8, 0))
        add_tooltip(model_label, tip("aircraft_model"))
        add_tooltip(self.entry_model, tip("aircraft_model"))
        for row, (key, text) in enumerate(AIRCRAFT_FIELDS, start=2):
            self._int_field(form, row, key, text)
        self._save_button(form, row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        right = ctk.CTkFrame(aircraft, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        panel = ctk.CTkFrame(right, corner_radius=10, border_width=1, border_color=BORDER)
        panel.grid(row=0, column=0, sticky="ew")
        panel.grid_columnconfigure(0, weight=1)
        self.goal_title = ctk.CTkLabel(panel, text=t("🎯 Sin objetivo"), font=self.font_title, anchor="w")
        self.goal_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.goal_bar = ctk.CTkProgressBar(panel, height=8)
        self.goal_bar.set(0)
        self.goal_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 6))
        self.goal_detail = ctk.CTkLabel(panel, text="", font=self.font_small, anchor="nw", justify="left", wraplength=300)
        self.goal_detail.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))
        panel.bind("<Configure>", lambda e: self.goal_detail.configure(wraplength=max(180, e.width - 26)))
        add_tooltip(self.goal_title, tip("goal"))
        ideas = ctk.CTkFrame(right, fg_color="transparent")
        ideas.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ideas.grid_columnconfigure((0, 1), weight=1, uniform="ideas")
        ctk.CTkLabel(ideas, text=t("IDEAS DE OBJETIVO · precio · plazas · rentabilidad estimada · llegada a tu ritmo"),
                     font=self.font_caption, text_color=MUTED, anchor="w").grid(row=0, column=0, columnspan=2, sticky="w")
        self.goal_ideas = [ctk.CTkLabel(ideas, text="", font=self.font_small, anchor="w", justify="left", wraplength=260)
                           for _ in range(2)]
        for column, label in enumerate(self.goal_ideas):
            label.grid(row=1, column=column, sticky="nw", padx=(0 if column == 0 else 12, 0))
        ideas.bind("<Configure>", lambda e: [label.configure(wraplength=max(160, e.width // 2 - 16)) for label in self.goal_ideas])

        # --- Opciones: switches in three columns, then campaign numbers, summary hour and Telegram
        options = tab("Opciones")
        self._columns(options, OPTION_SWITCHES, 3, self._switch)
        numbers = ctk.CTkFrame(options, fg_color="transparent")
        numbers.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self._columns(numbers, MARKETING_FIELDS + [("summary_hour", "Hora del resumen diario (0-23)")], 3, self._int_field)
        foot = ctk.CTkFrame(options, fg_color="transparent")
        foot.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        foot.grid_columnconfigure(0, weight=1)
        self.telegram_label = ctk.CTkLabel(foot, text=self._telegram_status(), font=self.font_small, text_color=MUTED, anchor="w")
        self.telegram_label.grid(row=0, column=0, sticky="w")
        self.btn_telegram_test = ctk.CTkButton(foot, text=t("Probar Telegram"), font=self.font, height=30, width=130,
                                               fg_color="transparent", border_width=1, border_color=BORDER,
                                               text_color=("#1f2328", "#e6edf3"), hover_color=("#eaeef2", "#21262d"),
                                               command=self.send_telegram_test)
        self.btn_telegram_test.grid(row=0, column=1, sticky="e", padx=(0, 8))
        add_tooltip(self.btn_telegram_test, tip("telegram_test"))
        self._save_button(foot, row=0, column=2, sticky="e")

        wanted = self.cfg.get("app", "default_tab", "Mercado")
        tabs.set(next((tab_title(name) for name in TAB_ICONS if name.lower() == wanted.lower()), tab_title("Mercado")))

    # ------------------------------------------------------------------ log (always visible)
    def _build_logs(self) -> None:
        frame = ctk.CTkFrame(self, border_width=1, border_color=BORDER)
        frame.grid(row=2, column=1, sticky="nsew", padx=16, pady=(0, 16))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text=t("📜  Registro"), font=self.font_title, anchor="w").grid(row=0, column=0, sticky="w")
        self.updated_label = ctk.CTkLabel(header, text=t("Sin datos todavía"), font=self.font_small, text_color=MUTED, anchor="w")
        self.updated_label.grid(row=0, column=1, sticky="w", padx=(14, 0))
        small_button = dict(height=28, font=self.font_small, fg_color="transparent", border_width=1, border_color=BORDER,
                            text_color=("#1f2328", "#e6edf3"), hover_color=("#eaeef2", "#21262d"))
        open_button = ctk.CTkButton(header, text=t("Abrir fichero"), width=100, command=self.open_log_file, **small_button)
        open_button.grid(row=0, column=2, padx=(0, 6))
        clear_button = ctk.CTkButton(header, text=t("Limpiar"), width=70, command=self.clear_logs, **small_button)
        clear_button.grid(row=0, column=3)
        add_tooltip(open_button, tip("open_log"))
        add_tooltip(clear_button, tip("clear_log"))

        self.tb_logs = ctk.CTkTextbox(frame, font=self.font_mono, wrap="word", state="disabled")
        self.tb_logs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        # Colour tags: timestamp, level, category and (for warnings / errors) the message itself.
        self.tb_logs.tag_config("ts", foreground="#8b949e")
        for level, (_label, _emoji, colour) in LEVEL_STYLES.items():
            self.tb_logs.tag_config(f"lvl_{level}", foreground=colour)
            self.tb_logs.tag_config(f"msg_{level}", foreground=colour)
        for _suffix, (label, _emoji, colour) in LOG_TAGS.items():
            self.tb_logs.tag_config(f"tag_{label}", foreground=colour)

    def _refresh_price_records(self) -> None:
        """Show the lowest price ever seen, in brackets, next to the fuel / CO2 price boxes."""
        records = self._state.get("price_records", {})
        for kind, label in self.record_labels.items():
            best = records.get(kind)
            series = self._history.series(kind)
            if series:
                seen_at, lowest = min(series, key=lambda item: (item[1], -item[0]))
                if not best or lowest < best[0]:
                    best = [lowest, seen_at]
            if best:
                label.configure(text=t("(mín. visto ${price})", price=fmt(best[0])))
                label.tooltip.text = time.strftime(t("Precio más bajo visto: ${price} el %d/%m/%Y a las %H:%M",
                                                     price=fmt(best[0])), time.localtime(best[1]))
            else:
                label.configure(text="")

    # ------------------------------------------------------------------ periodic refresh
    def _poll(self) -> None:
        while True:
            try:
                action = self._actions.get_nowait()
            except queue.Empty:
                break
            if action == "start":
                self.start_bot()
            elif action == "quit":
                self.on_close()
                return
        # Each step is guarded and the next poll is always scheduled: one error used to stop this loop,
        # which froze the log and the status in the window while the bot kept running.
        for step in (self._drain_logs, self._refresh_status, self._refresh_stats, self._maybe_sync):
            self._guarded(step)
        self.after(500, self._poll)

    def _maybe_sync(self) -> None:
        if self.cfg.version != self._cfg_seen:
            self._sync_from_config()

    def _guarded(self, step) -> None:
        try:
            step()
        except Exception:  # noqa: BLE001 - the window must keep refreshing whatever happens
            now = time.time()
            if now - self._ui_error_at > 60:  # at most one report a minute, the loop runs twice a second
                self._ui_error_at = now
                log.exception("Error al refrescar la ventana (%s); sigo.", getattr(step, "__name__", "?"))

    def report_callback_exception(self, exc, val, tb) -> None:
        """Errors in buttons and timers go to the log file (with pythonw there is no console to print them)."""
        log.error("Error en la ventana: %s", val, exc_info=(exc, val, tb))

    def _drain_logs(self) -> None:
        records = []
        while True:
            try:
                records.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if not records:
            return
        self.tb_logs.configure(state="normal")
        for record in records:
            self._insert_record(record)
        line_count = int(self.tb_logs.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.tb_logs.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")
        self.tb_logs.see("end")
        self.tb_logs.configure(state="disabled")

    def _insert_record(self, record: logging.LogRecord) -> None:
        """One log line: [hh:mm:ss] [NIVEL] [TAG] emoji mensaje, each part in its own colour."""
        level_label, level_emoji, _colour = LEVEL_STYLES.get(record.levelname, LEVEL_STYLES["INFO"])
        tag_label, tag_emoji, _colour = log_tag(record.name)
        emoji = level_emoji or tag_emoji
        self.tb_logs.insert("end", time.strftime("[%H:%M:%S] ", time.localtime(record.created)), "ts")
        self.tb_logs.insert("end", f"[{level_label}] ", f"lvl_{record.levelname}")
        self.tb_logs.insert("end", f"[{tag_label}] ", f"tag_{tag_label}")
        message_tag = f"msg_{record.levelname}" if record.levelname in ("WARNING", "ERROR", "CRITICAL") else "msg"
        self.tb_logs.insert("end", f"{emoji} {record.getMessage()}\n", message_tag)

    def _refresh_status(self) -> None:
        state = self.bot.state
        alive = self.bot.is_alive()
        mode = self.bot.stats().mode
        self.mode_label.configure(text=t("Juego en modo {mode}", mode=t(mode)) if mode else "")
        self.status_pill.configure(text=f"●  {t(state.value).upper()}", fg_color=PILL_COLORS[state])

        self.btn_start.configure(state="disabled" if alive else "normal")
        self.btn_stop.configure(state="normal" if alive and state is not BotState.STOPPING else "disabled")
        # Read once: the bot thread sets it to None when a cycle starts, possibly between two reads here.
        next_at = self.bot.next_cycle_at
        waiting = alive and state is BotState.RUNNING and next_at is not None
        self.btn_run_now.configure(state="normal" if waiting else "disabled")
        for entry in (self.entry_user, self.entry_pass):
            entry.configure(state="disabled" if alive else "normal")

        if waiting and next_at is not None:
            self.next_label.configure(text=t("Próxima revisión en {time}", time=fmt_clock(max(0, int(next_at - time.time())))))
        elif alive and state is BotState.RUNNING:
            self.next_label.configure(text=t("Revisando ..."))
        elif self.restart.restart_at is not None:
            text = t("Reinicio automático en {time}", time=fmt_clock(self.restart.restart_in))
            if state is BotState.ERROR and self.bot.last_error:
                text = f"{self.bot.last_error}\n{text}"
            self.next_label.configure(text=text)
        elif state is BotState.ERROR and self.bot.last_error:
            self.next_label.configure(text=self.bot.last_error)
        else:
            self.next_label.configure(text="")
        enabled = self.option_vars.get("auto_restart", tk.BooleanVar(value=False)).get()
        if self.restart.tick(alive, state, enabled):
            self.start_bot()

    def _refresh_stats(self) -> None:
        snap = snapshot(self.bot, self.cfg, self._state, self._market)

        def show(key: str, value: str, sub: str = "", fraction: Optional[float] = None) -> None:
            value_label, sub_label, bar = self.tiles[key]
            value_label.configure(text=value)
            sub_label.configure(text=sub)
            if bar is not None:
                bar.set(max(0.0, min(1.0, fraction or 0.0)))

        money, income = snap["money"], snap["income_day"]
        show("money", f"${fmt(money)}" if money is not None else "-",
             " · ".join(part for part in (t("+{money}/día", money=fmt_money(income)) if income is not None else "",
                                          t("{n} puntos", n=fmt(snap["points"])) if snap["points"] is not None else "")
                        if part))
        reputation = snap["reputation"]
        show("reputation", f"{reputation} %" if reputation is not None else "-",
             t("campaña {time}", time=fmt_clock(snap["campaign_left"])) if snap["campaign_left"] else t("sin campaña activa"),
             (reputation or 0) / 100)
        for kind in ("fuel", "co2"):
            tank = snap[kind]
            parts = [f"${fmt(tank['price'])}" if tank["price"] is not None else "",
                     t("compra ≤ {price}", price=fmt(tank["buy_at"])) if tank["buy_at"] is not None else ""]
            show(kind, f"{tank['pct']:.0f} %" if tank["pct"] is not None else "-", " · ".join(p for p in parts if p),
                 (tank["pct"] or 0) / 100)
        fleet = snap["fleet"]
        parts = [t("{n} en vuelo", n=fleet["inflight"]) if fleet["inflight"] else "",
                 t("{n} aparc.", n=fleet["parked"]) if fleet["parked"] else "",
                 t("{n} pend.", n=fleet["pending"]) if fleet["pending"] else ""]
        show("fleet", fmt(fleet["size"]) if fleet["size"] is not None else "-", " · ".join(p for p in parts if p))
        goal = snap["goal"]
        name = (goal["name"] or "").removeprefix(t("Auto: {name}", name=""))
        show("goal", f"{goal['pct']:.0f} %" if goal["pct"] is not None else "-",
             " · ".join(p for p in (name, goal["eta_text"] or "") if p), (goal["pct"] or 0) / 100)
        if snap["updated_at"]:
            self.updated_label.configure(text=t("actualizado {time}", time=time.strftime("%H:%M:%S", time.localtime(snap["updated_at"]))))

    # -- values used by the goal panel
    def _money(self) -> Optional[int]:
        return last_money(self.bot, self._state)

    def _income(self) -> Optional[int]:
        rate = self.bot.stats().income_day
        return rate if rate is not None else income_per_day(self._state)

    def _goal_values(self) -> list[str]:
        models = sorted((m for m in self._market if m.get("capacity", 0) >= 100), key=lambda m: -m.get("price", 0))
        return [t(AUTO_GOAL_LABEL)] + [m["name"] for m in models]

    def _refresh_goal_panel(self) -> None:
        goal = goal_status(self.cfg, self._market, self._money(), self._income(), goal_text=self.goal_combo.get(),
                           live_price=self.bot.stats().goal_price)
        name, price, progress = goal["name"], goal["price"], goal["progress"]
        saving = self.option_vars["save_for_goal"].get()
        stats = self.bot.stats()
        if not name:
            self.goal_title.configure(text=t("🎯 Elige un avión objetivo"))
            self.goal_bar.set(0)
            self.goal_detail.configure(text=t("Escribe o elige un modelo en «Avión objetivo» y pulsa Guardar ajustes."))
        elif not price:
            self.goal_title.configure(text=f"🎯 {name}")
            self.goal_bar.set(0)
            self.goal_detail.configure(text=t("No encuentro ese modelo en el mercado guardado. Revisa el nombre o espera a "
                                              "que el bot consulte el mercado."))
        else:
            self.goal_title.configure(text=f"🎯 {name} · {fmt_money(price)}")
            lines = []
            if progress:
                self.goal_bar.set(progress["pct"] / 100)
                lines.append(t("Ahorrado {have} ({pct}%), la reserva aparte.", have=fmt_money(progress["have"]),
                                pct=f"{progress['pct']:.0f}"))
                if progress["reached"]:
                    lines.append(t("¡Ya llega! Lo pedirá en la próxima revisión si hay hueco en el hangar."))
                else:
                    rate = self._income()
                    rate_text = t("{money}/día", money=fmt_money(rate)) if rate is not None else t("ritmo aún sin medir")
                    lines.append(t("Faltan {missing} · {rate} · llegada {eta}", missing=fmt_money(progress["missing"]),
                                   rate=rate_text, eta=fmt_days(progress["eta_days"])))
            else:
                self.goal_bar.set(0)
            if stats.hangar_free is not None:
                lines.append(t("Hangar: {free} huecos libres de {total}", free=stats.hangar_free, total=fmt(stats.hangar_capacity)))
            if not saving:
                lines.append(t("Modo ahorro apagado: compra el avión más rentable que pueda."))
            elif self.option_vars["goal_invest"].get():
                lines.append(t("Compra pequeños solo si se amortizan antes de llegar."))
            else:
                lines.append(t("Solo ahorra: no compra otros aviones."))
            self.goal_detail.configure(text="\n".join(lines))
        for label, lines in zip(self.goal_ideas, self._goal_ideas()):
            label.configure(text="\n".join(lines))

    def _goal_ideas(self) -> tuple[list[str], list[str]]:
        """Left: the next steps of the growth ladder as income grows. Right: big 'whim' aircraft and their payback."""
        priced = [m for m in self._market if m.get("price") and m.get("profit")]
        if not priced:
            return [t("El bot guardará la lista del mercado la próxima vez que lo consulte.")], []

        def line(m: dict) -> str:
            return t("{name} · {price} · {seats} pax · gana {profit}/día · se paga en {days} d", name=m["name"],
                     price=fmt_money(m["price"]), seats=m["capacity"], profit=fmt_money(m["profit"]),
                     days=f"{m['price'] / m['profit']:.1f}")

        rate = self._income() or 0
        ladder: list[dict] = []
        for factor in (1, 1.6, 2.5, 4):
            step = ladder_step(self.cfg, self._market, int(rate * factor), self._money()) if rate else None
            if step and step not in ladder:
                ladder.append(step)
        left = [t("Escalera (a tu ritmo actual y al crecer):")] + [line(m) for m in ladder] if ladder else []
        right = [t("Caprichos:")] + [line(m) for name in ICONIC_GOALS if (m := find_model(priced, name))]
        return left, right

    # -- files written by the bot: prices, state (purchases, money samples), market
    def _changed(self, path: Path) -> bool:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return False
        if self._mtimes.get(str(path)) == mtime:
            return False
        self._mtimes[str(path)] = mtime
        return True

    def _refresh_files(self) -> None:
        self._guarded(self._reload_files)
        self.after(15000, self._refresh_files)

    def _reload_files(self) -> None:
        if self._changed(history_file()):
            self._history.load()
        if self._changed(state_file()):
            self._state = load_state()
        if self._changed(market_file()):
            self._market = load_market()
            self.goal_combo.configure(values=self._goal_values())
        self._refresh_price_records()
        self._refresh_goal_panel()

    def _sync_from_config(self) -> None:
        """Show settings changed from the web dashboard (never overwriting the box the user is typing in)."""
        focused = self.focus_get()

        def typing(widget) -> bool:
            return focused is not None and focused in (widget, getattr(widget, "_entry", None))

        for key, entry in self.setting_entries.items():
            value = str(self.cfg.get_int("settings", key))
            if entry.get() != value and not typing(entry):
                entry.delete(0, "end")
                entry.insert(0, value)
        for key, var in self.option_vars.items():
            var.set(self.cfg.get_bool("options", key, OPTION_DEFAULTS.get(key, False)))
        goal = self.cfg.get("settings", "goal_model")
        goal = t(AUTO_GOAL_LABEL) if is_auto_goal(goal) else goal
        if self.goal_combo.get() != goal and not typing(self.goal_combo):
            self.goal_combo.set(goal)
        model = self.cfg.get("settings", "aircraft_model")
        if self.entry_model.get() != model and not typing(self.entry_model):
            self.entry_model.delete(0, "end")
            if model:
                self.entry_model.insert(0, model)
        self._cfg_seen = self.cfg.version
        self._refresh_goal_panel()

    # ------------------------------------------------------------------ actions
    def start_bot(self) -> None:
        if self.bot.is_alive():
            return
        # Another copy of this profile (here without our own web server, or on another machine such as the
        # Raspberry) would play the same airline: never start a second bot.
        where = running_instance(self.cfg, include_local=self.web is None or self.web.server is None)
        if where:
            place = "en este equipo" if where == "127.0.0.1" else f"en {where}"
            log.warning("Ya hay otro Airline Manager 4 Bot de este perfil en marcha %s: no arranco un segundo bot. "
                        "Páralo antes allí.", place)
            return
        if not self._save_settings(silent=True):
            return
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        self.cfg.set_credentials(username, password, persist=self.var_remember.get())
        self.bot.start()

    def stop_bot(self) -> None:
        log.info("Parando tras el paso actual ...")
        self.bot.stop()

    def _save_settings(self, silent: bool = False) -> bool:
        values: dict[str, int] = {}
        for key, label in ALL_FIELDS:
            value = parse_int(self.setting_entries[key].get())
            if value is None:
                log.warning("'%s' debe ser un número entero.", label)
                return False
            values[key] = value
        for key, value in clamp_settings(values).items():
            self.cfg.set("settings", key, value)
            entry = self.setting_entries[key]
            entry.delete(0, "end")
            entry.insert(0, str(value))
        self.cfg.set("settings", "aircraft_model", self.entry_model.get().strip())
        goal = self.goal_combo.get().strip()
        if is_auto_goal(goal):
            goal = "auto"
            self.goal_combo.set(t(AUTO_GOAL_LABEL))
        elif known := find_model(self._market, goal):
            goal = known["name"]
            self.goal_combo.set(goal)
        elif goal and self._market:
            log.warning("No encuentro «%s» en el mercado guardado; el bot lo buscará igualmente por nombre.", goal)
        self.cfg.set("settings", "goal_model", goal)
        self.cfg.save()
        self._cfg_seen = self.cfg.version
        if not silent:
            log.info("Ajustes guardados.")
        self._refresh_goal_panel()
        return True

    def _on_option(self, key: str) -> None:
        self.cfg.set("options", key, "on" if self.option_vars[key].get() else "off")
        self.cfg.save()
        self._cfg_seen = self.cfg.version
        if key == "dry_run":
            if self.option_vars[key].get():
                log.info("Simulación activada: el bot solo registra lo que compraría o planificaría.")
            else:
                log.info("Simulación desactivada: el bot gastará dinero de verdad.")
        if key in ("save_for_goal", "goal_invest"):
            self._refresh_goal_panel()
        if key in ("auto_marketing", "marketing_eco"):
            self.bot.marketing_next_check = 0.0  # look at the campaigns again in the next cycle

    def _on_remember_toggle(self) -> None:
        remember = self.var_remember.get()
        self.cfg.set("options", "remember_credentials", "on" if remember else "off")
        self.cfg.save()
        if not remember and self.cfg.forget_credentials():
            log.info("Credenciales guardadas eliminadas (config/secrets.ini).")

    # -- profiles: each one is a separate airline / game account with its own window, data and web port
    def _profile_values(self) -> list[str]:
        return [profile.label for profile in paths.all_profiles()] + [t(PROFILE_NEW)]

    def _on_profile(self, choice: str) -> None:
        self.profile_menu.set(self.cfg.profile.label)
        if choice == t(PROFILE_NEW):
            self._new_profile()
        elif choice != self.cfg.profile.label:
            self._open_profile(paths.Profile("" if choice == paths.MAIN_LABEL else choice))

    def _new_profile(self) -> None:
        dialog = ctk.CTkInputDialog(title=t("Nuevo perfil"), text=t("Nombre del perfil nuevo (por ejemplo «realismo»).\n"
                                                                    "Tendrá su propia cuenta, ajustes, datos y panel web."))
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        try:
            profile = paths.create(name, source=self.cfg.profile)
        except ValueError as exc:
            log.warning("%s", exc)
            return
        log.info("Perfil «%s» creado con tus ajustes actuales (panel web en el puerto %d). Escribe su cuenta en la "
                 "ventana que se abre.", profile.label, profile.port())
        shortcut = create_desktop_shortcut(profile)
        if shortcut:
            log.info("Acceso directo «%s» creado en el escritorio.", shortcut.removesuffix(".lnk"))
        self.profile_menu.configure(values=self._profile_values())
        self._open_profile(profile)

    def _open_profile(self, profile: paths.Profile) -> None:
        if profile_running(profile):
            log.info("El perfil «%s» ya está abierto: abro su panel web.", profile.label)
            token = profile_token(profile)
            webbrowser.open_new_tab(f"http://127.0.0.1:{profile.port()}/" + (f"?token={token}" if token else ""))
            return
        log.info("Abriendo el perfil «%s» en otra ventana ...", profile.label)
        launch(profile)

    def open_web(self) -> None:
        if self.web is None or not self.web.url:
            log.info("El panel web está desactivado ([web] enabled en config/settings.ini).")
            return
        token = self.cfg.web_token
        webbrowser.open_new_tab(self.web.url + (f"?token={token}" if token else ""))

    def _telegram_status(self) -> str:
        self.cfg.reload_secrets()
        token, chat_id = self.cfg.telegram
        if token and chat_id:
            return t("Telegram configurado para el chat {chat} (config/secrets.ini).", chat=chat_id)
        return t("Telegram sin configurar: añade bot_token y chat_id en la sección [telegram] de config/secrets.ini.")

    def send_telegram_test(self) -> None:
        self.telegram_label.configure(text=self._telegram_status())
        client = Telegram(*self.cfg.telegram)
        if not client.enabled:
            log.warning("Telegram no está configurado todavía (config/secrets.ini, sección [telegram]).")
            return
        self.btn_telegram_test.configure(state="disabled")

        def worker() -> None:
            ok, description = client.send_now("✅ <b>Airline Manager 4 Bot</b> conectado a Telegram.")
            if ok:
                log.info("Mensaje de prueba enviado a Telegram.")
            else:
                log.warning("La prueba de Telegram ha fallado: %s", description)
            self.after(0, lambda: self.btn_telegram_test.configure(state="normal"))

        threading.Thread(target=worker, name="telegram-test", daemon=True).start()

    def _show_web_link(self) -> None:
        if self.web is not None and self.web.url:
            self.web_label.configure(text=t("🌐  Abrir el panel web"))
            self.web_label.tooltip.text = t("Abre {url} en el navegador: las mismas estadísticas, registro y ajustes.",
                                            url=self.web.url)

    def change_language(self, label: str) -> None:
        """New interface language: redraw the window (the bot keeps running) and switch the game account too."""
        code = next((code for code, name in LANGUAGES.items() if name == label), "es")
        if code == language():
            return
        self.cfg.set("app", "language", code)
        self.cfg.save()
        set_language(code)
        self.bot.request_game_language()
        self._rebuild_ui()
        log.info("Idioma de la interfaz: %s. El del juego se cambia en la próxima revisión.", LANGUAGES[code])

    def _rebuild_ui(self) -> None:
        self._save_settings(silent=True)  # numbers typed but not saved yet survive the redraw
        for child in self.winfo_children():
            child.destroy()
        self.setting_entries.clear()
        self.option_vars.clear()
        self._build_sidebar()
        self._build_tiles()
        self._build_tabs()
        self._build_logs()
        self._show_web_link()
        self.tb_logs.configure(state="normal")
        for line in self.log_buffer.since(0)[-MAX_LOG_LINES:]:
            self._insert_line(line)
        self.tb_logs.see("end")
        self.tb_logs.configure(state="disabled")
        self._cfg_seen = self.cfg.version
        for step in (self._refresh_price_records, self._refresh_goal_panel, self._refresh_status, self._refresh_stats):
            self._guarded(step)

    def _insert_line(self, line: dict) -> None:
        """A line kept by the LogBuffer, painted like _insert_record does."""
        level = line.get("level_key", "INFO")
        self.tb_logs.insert("end", time.strftime("[%H:%M:%S] ", time.localtime(line["time"])), "ts")
        self.tb_logs.insert("end", f"[{line['level']}] ", f"lvl_{level}")
        self.tb_logs.insert("end", f"[{line['tag']}] ", f"tag_{line['tag']}")
        message_tag = f"msg_{level}" if level in ("WARNING", "ERROR", "CRITICAL") else "msg"
        self.tb_logs.insert("end", f"{line['emoji']} {line['message']}\n", message_tag)

    def change_theme(self, label: str) -> None:
        mode = {text: name for name, text in theme_labels().items()}.get(label, "System")
        ctk.set_appearance_mode(mode)
        self.cfg.set("app", "appearance_mode", mode)
        self.cfg.save()

    def clear_logs(self) -> None:
        self.tb_logs.configure(state="normal")
        self.tb_logs.delete("1.0", "end")
        self.tb_logs.configure(state="disabled")

    def open_log_file(self) -> None:
        path = self.log_file.resolve()
        if not path.exists():
            log.info("Aún no hay fichero de registro.")
            return
        system = platform.system()
        if system == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def on_close(self) -> None:
        if self.bot.is_alive():
            log.info("Cerrando: parando el bot ...")
            self.bot.stop()
            # Closing Chrome and chromedriver can take a while mid-cycle; leaving earlier orphans chromedriver.
            self.bot.join(timeout=20)
            if self.bot.is_alive():
                self.bot.kill_browser()
        if self.web is not None:
            self.web.stop()
        self.destroy()
