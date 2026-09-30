"""customtkinter GUI for Airline Manager 4 Bot."""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import queue
import subprocess
import time
import tkinter as tk
import webbrowser
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from bot import Bot, BotState, fmt
from config import AppConfig

log = logging.getLogger("am4bot")

AUTHOR_URL = "https://github.com/JavierOlmedo"
LOG_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"
MAX_LOG_LINES = 800
WINDOW_SIZE = (1000, 640)

STATE_COLORS = {
    BotState.IDLE: "#8a8d91",
    BotState.STARTING: "#f5a623",
    BotState.LOGGING_IN: "#f5a623",
    BotState.RUNNING: "#2ecc71",
    BotState.STOPPING: "#f5a623",
    BotState.ERROR: "#e74c3c",
}

SETTING_FIELDS = [
    ("fuel_price_good", "Good fuel price ($)"),
    ("co2_price_good", "Good CO2 price ($)"),
    ("fuel_quantity_buy", "Fuel to buy"),
    ("co2_quantity_buy", "CO2 to buy"),
    ("cycle_min_minutes", "Min wait (minutes)"),
    ("cycle_max_minutes", "Max wait (minutes)"),
]

OPTION_SWITCHES = [
    ("auto_depart", "Auto depart aircraft"),
    ("autobuy_fuel", "Auto buy fuel"),
    ("autobuy_co2", "Auto buy CO2"),
    ("start_on_launch", "Start bot on launch"),
    ("keep_session", "Keep browser session"),
    ("headless", "Headless browser"),
]

MUTED = ("gray40", "gray65")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig()
        self.bot = Bot(self.cfg)
        self.log_queue: "queue.Queue[logging.LogRecord]" = queue.Queue()
        self.log_file = self._setup_logging()

        ctk.set_appearance_mode(self.cfg.get("app", "appearance_mode", "System"))
        ctk.set_default_color_theme(self.cfg.get("app", "color_theme", "blue"))

        self.title(self.cfg.get("app", "title", "Airline Manager 4 Bot"))
        self._set_icon()
        self.minsize(900, 580)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.font = ctk.CTkFont(size=13)
        self.font_bold = ctk.CTkFont(size=13, weight="bold")
        self.font_title = ctk.CTkFont(size=15, weight="bold")
        self.font_small = ctk.CTkFont(size=11)
        mono = {"Windows": "Consolas", "Darwin": "Menlo"}.get(platform.system(), "DejaVu Sans Mono")
        self.font_mono = ctk.CTkFont(family=mono, size=12)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_sidebar()
        self._build_cards()
        self._build_logs()
        self._center()

        log.info("GUI loaded.")
        self.after(300, self._poll)
        if self.cfg.get_bool("options", "start_on_launch"):
            self.after(600, self.start_bot)

    # ------------------------------------------------------------------ setup
    def _setup_logging(self) -> Path:
        logger = logging.getLogger("am4bot")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", LOG_DATE_FORMAT)

        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO)
        queue_handler.setFormatter(formatter)
        logger.addHandler(queue_handler)

        log_file = Path(self.cfg.get("app", "log_file", "data/logs/am4bot.log"))
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:  # an old plain file named "logs" is in the way
            log_file = Path("data") / log_file.name
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logging.getLogger("selenium").setLevel(logging.WARNING)
        return log_file

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
        x = (self.winfo_screenwidth() - width) // 2
        y = max((self.winfo_screenheight() - height) // 2 - 30, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ------------------------------------------------------------------ widgets
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(10, weight=1)

        banner = ctk.CTkImage(Image.open("assets/banner.png"), size=(196, 46))
        ctk.CTkLabel(sidebar, text="", image=banner).grid(row=0, column=0, padx=20, pady=(26, 22))

        ctk.CTkLabel(sidebar, text="ACCOUNT", font=self.font_small, text_color=MUTED, anchor="w").grid(
            row=1, column=0, padx=22, sticky="ew"
        )
        username, password = self.cfg.credentials
        self.entry_user = ctk.CTkEntry(sidebar, placeholder_text="E-mail", font=self.font, height=32)
        self.entry_user.grid(row=2, column=0, padx=20, pady=(4, 6), sticky="ew")
        self.entry_pass = ctk.CTkEntry(sidebar, placeholder_text="Password", show="•", font=self.font, height=32)
        self.entry_pass.grid(row=3, column=0, padx=20, sticky="ew")
        # Inserting an empty string would hide the placeholder text.
        if username:
            self.entry_user.insert(0, username)
        if password:
            self.entry_pass.insert(0, password)

        self.var_remember = tk.BooleanVar(value=self.cfg.get_bool("options", "remember_credentials", True))
        ctk.CTkCheckBox(
            sidebar, text="Remember credentials", variable=self.var_remember, font=self.font_small,
            checkbox_width=18, checkbox_height=18, command=self._on_remember_toggle,
        ).grid(row=4, column=0, padx=22, pady=(8, 18), sticky="w")

        self.btn_start = ctk.CTkButton(sidebar, text="START BOT", font=self.font_bold, height=38, command=self.start_bot)
        self.btn_start.grid(row=5, column=0, padx=20, sticky="ew")
        self.btn_stop = ctk.CTkButton(
            sidebar, text="STOP BOT", font=self.font_bold, height=38, fg_color="#c0392b", hover_color="#96281b",
            state="disabled", command=self.stop_bot,
        )
        self.btn_stop.grid(row=6, column=0, padx=20, pady=(8, 0), sticky="ew")
        self.btn_run_now = ctk.CTkButton(
            sidebar, text="Run cycle now", font=self.font, height=30, fg_color="transparent", border_width=1,
            text_color=("gray10", "gray90"), state="disabled", command=self.bot.run_now,
        )
        self.btn_run_now.grid(row=7, column=0, padx=20, pady=(8, 0), sticky="ew")

        status = ctk.CTkFrame(sidebar, fg_color="transparent")
        status.grid(row=8, column=0, padx=20, pady=(22, 0), sticky="ew")
        self.status_dot = ctk.CTkLabel(status, text="●", font=ctk.CTkFont(size=18), text_color=STATE_COLORS[BotState.IDLE], width=20)
        self.status_dot.grid(row=0, column=0, sticky="w")
        self.status_label = ctk.CTkLabel(status, text=BotState.IDLE.value, font=self.font_bold, anchor="w", justify="left", wraplength=170)
        self.status_label.grid(row=0, column=1, padx=(4, 0), sticky="w")
        self.next_label = ctk.CTkLabel(sidebar, text="", font=self.font_small, text_color=MUTED, anchor="w")
        self.next_label.grid(row=9, column=0, padx=22, pady=(2, 0), sticky="ew")

        ctk.CTkLabel(sidebar, text="APPEARANCE", font=self.font_small, text_color=MUTED, anchor="w").grid(
            row=11, column=0, padx=22, sticky="ew"
        )
        self.theme_menu = ctk.CTkOptionMenu(sidebar, values=["Light", "Dark", "System"], command=self.change_theme, font=self.font)
        self.theme_menu.set(self.cfg.get("app", "appearance_mode", "System"))
        self.theme_menu.grid(row=12, column=0, padx=20, pady=(4, 12), sticky="ew")

        author = ctk.CTkLabel(sidebar, text="Javier Olmedo", font=self.font_bold, cursor="hand2")
        author.grid(row=13, column=0, padx=20, pady=(0, 16))
        author.bind("<Button-1>", lambda _event: webbrowser.open_new_tab(AUTHOR_URL))

    def _card(self, parent: ctk.CTkFrame, column: int, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 10, 0))
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=self.font_title, anchor="w").grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="nsew")
        return body

    def _build_cards(self) -> None:
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=1, sticky="nsew", padx=16, pady=(16, 8))
        for column in range(3):
            top.grid_columnconfigure(column, weight=1, uniform="cards")

        # --- statistics
        stats = self._card(top, 0, "Statistics")
        stats.grid_columnconfigure(1, weight=1)
        self.stat_labels: dict[str, ctk.CTkLabel] = {}
        rows = [("money", "Money"), ("points", "Points"), ("fuel", "Fuel"), ("co2", "CO2"), ("fuel_price", "Fuel price"), ("co2_price", "CO2 price")]
        row = 0
        for key, text in rows:
            ctk.CTkLabel(stats, text=text, font=self.font, text_color=MUTED, anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            value = ctk.CTkLabel(stats, text="-", font=self.font_bold, anchor="e")
            value.grid(row=row, column=1, sticky="e", pady=2)
            self.stat_labels[key] = value
            row += 1
            if key in ("fuel", "co2"):
                bar = ctk.CTkProgressBar(stats, height=8)
                bar.set(0)
                bar.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
                setattr(self, f"bar_{key}", bar)
                row += 1
        self.updated_label = ctk.CTkLabel(stats, text="Not updated yet", font=self.font_small, text_color=MUTED, anchor="w")
        self.updated_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # --- settings
        settings = self._card(top, 1, "Settings")
        settings.grid_columnconfigure(0, weight=1)
        self.setting_entries: dict[str, ctk.CTkEntry] = {}
        for row, (key, text) in enumerate(SETTING_FIELDS):
            ctk.CTkLabel(settings, text=text, font=self.font, anchor="w").grid(row=row, column=0, sticky="w", pady=3)
            entry = ctk.CTkEntry(settings, width=84, height=28, font=self.font_bold, justify="right")
            entry.insert(0, str(self.cfg.get_int("settings", key)))
            entry.grid(row=row, column=1, sticky="e", pady=3)
            self.setting_entries[key] = entry
        ctk.CTkButton(settings, text="Save settings", font=self.font, height=30, command=self._save_settings).grid(
            row=len(SETTING_FIELDS), column=0, columnspan=2, sticky="ew", pady=(12, 0)
        )

        # --- options
        options = self._card(top, 2, "Options")
        self.option_vars: dict[str, tk.BooleanVar] = {}
        for row, (key, text) in enumerate(OPTION_SWITCHES):
            var = tk.BooleanVar(value=self.cfg.get_bool("options", key))
            ctk.CTkSwitch(options, text=text, variable=var, onvalue=True, offvalue=False, font=self.font,
                          command=lambda k=key: self._on_option(k)).grid(row=row, column=0, sticky="w", pady=4)
            self.option_vars[key] = var

    def _build_logs(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=12)
        frame.grid(row=1, column=1, sticky="nsew", padx=16, pady=(8, 16))
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Logs", font=self.font_title, anchor="w").grid(row=0, column=0, sticky="w")
        small_button = dict(height=26, font=self.font_small, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        ctk.CTkButton(header, text="Open log file", width=100, command=self.open_log_file, **small_button).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(header, text="Clear", width=60, command=self.clear_logs, **small_button).grid(row=0, column=2)

        self.tb_logs = ctk.CTkTextbox(frame, font=self.font_mono, wrap="word", state="disabled")
        self.tb_logs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))

    # ------------------------------------------------------------------ periodic refresh
    def _poll(self) -> None:
        self._drain_logs()
        self._refresh_status()
        self._refresh_stats()
        self.after(500, self._poll)

    def _drain_logs(self) -> None:
        lines = []
        while True:
            try:
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            lines.append(record.getMessage())
        if lines:
            self._append_log("\n".join(lines) + "\n")

    def _append_log(self, text: str) -> None:
        self.tb_logs.configure(state="normal")
        self.tb_logs.insert("end", text)
        line_count = int(self.tb_logs.index("end-1c").split(".")[0])
        if line_count > MAX_LOG_LINES:
            self.tb_logs.delete("1.0", f"{line_count - MAX_LOG_LINES}.0")
        self.tb_logs.see("end")
        self.tb_logs.configure(state="disabled")

    def _refresh_status(self) -> None:
        state = self.bot.state
        alive = self.bot.is_alive()
        text = state.value
        if state is BotState.ERROR and self.bot.last_error:
            text = f"Error: {self.bot.last_error}"
        self.status_dot.configure(text_color=STATE_COLORS[state])
        self.status_label.configure(text=text)

        self.btn_start.configure(state="disabled" if alive else "normal")
        self.btn_stop.configure(state="normal" if alive and state is not BotState.STOPPING else "disabled")
        waiting = alive and state is BotState.RUNNING and self.bot.next_cycle_at is not None
        self.btn_run_now.configure(state="normal" if waiting else "disabled")
        for entry in (self.entry_user, self.entry_pass):
            entry.configure(state="disabled" if alive else "normal")

        if waiting:
            remaining = max(0, int(self.bot.next_cycle_at - time.time()))
            self.next_label.configure(text=f"Next check in {remaining // 60:02d}:{remaining % 60:02d}")
        elif alive and state is BotState.RUNNING:
            self.next_label.configure(text="Checking now ...")
        else:
            self.next_label.configure(text="")

    def _refresh_stats(self) -> None:
        stats = self.bot.stats()
        self.stat_labels["money"].configure(text=f"$ {fmt(stats.money)}" if stats.money is not None else "-")
        self.stat_labels["points"].configure(text=fmt(stats.points) if stats.points is not None else "-")
        for key in ("fuel", "co2"):
            holding = getattr(stats, key)
            capacity = getattr(stats, f"{key}_capacity")
            price = getattr(stats, f"{key}_price")
            if holding is None:
                self.stat_labels[key].configure(text="-")
            elif capacity:
                self.stat_labels[key].configure(text=f"{fmt(holding)} / {fmt(capacity)}")
            else:
                self.stat_labels[key].configure(text=fmt(holding))
            getattr(self, f"bar_{key}").set(min(holding / capacity, 1.0) if holding is not None and capacity else 0)
            self.stat_labels[f"{key}_price"].configure(text=f"$ {fmt(price)}" if price is not None else "-")
        if stats.updated_at:
            self.updated_label.configure(text="Updated " + time.strftime("%H:%M:%S", time.localtime(stats.updated_at)))

    # ------------------------------------------------------------------ actions
    def start_bot(self) -> None:
        if self.bot.is_alive():
            return
        if not self._save_settings(silent=True):
            return
        username = self.entry_user.get().strip()
        password = self.entry_pass.get()
        self.cfg.set_credentials(username, password, persist=self.var_remember.get())
        self.bot.start()

    def stop_bot(self) -> None:
        log.info("Stopping after the current step ...")
        self.bot.stop()

    def _save_settings(self, silent: bool = False) -> bool:
        values: dict[str, int] = {}
        for key, label in SETTING_FIELDS:
            raw = self.setting_entries[key].get().strip().replace(",", "").replace(".", "")
            if not raw.isdigit():
                log.warning("'%s' must be a whole number.", label)
                return False
            values[key] = int(raw)
        if values["cycle_min_minutes"] < 1:
            values["cycle_min_minutes"] = 1
        if values["cycle_max_minutes"] < values["cycle_min_minutes"]:
            values["cycle_max_minutes"] = values["cycle_min_minutes"]
        for key, value in values.items():
            self.cfg.set("settings", key, value)
            entry = self.setting_entries[key]
            entry.delete(0, "end")
            entry.insert(0, str(value))
        self.cfg.save()
        if not silent:
            log.info("Settings saved.")
        return True

    def _on_option(self, key: str) -> None:
        self.cfg.set("options", key, "on" if self.option_vars[key].get() else "off")
        self.cfg.save()

    def _on_remember_toggle(self) -> None:
        remember = self.var_remember.get()
        self.cfg.set("options", "remember_credentials", "on" if remember else "off")
        self.cfg.save()
        if not remember and self.cfg.forget_credentials():
            log.info("Saved credentials deleted (config/secrets.ini).")

    def change_theme(self, mode: str) -> None:
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
            log.info("No log file yet.")
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
            log.info("Closing: stopping the bot ...")
            self.bot.stop()
            self.bot.join(timeout=6)
            if self.bot.is_alive():
                self.bot.kill_browser()
        self.destroy()
