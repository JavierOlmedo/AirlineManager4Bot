"""Entry point: ``python src/main.py`` from any working directory.

``python src/main.py --web`` runs the bot with only the web dashboard (no desktop window), for example on
a machine that stays on all day: open the address it prints in a browser.

``--profile <name>`` runs another airline (game account) with its own settings, credentials, Chrome session,
data and web port in profiles/<name>/ (created from the main settings the first time). See paths.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_desktop() -> None:
    from app import App

    app = App()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.on_close()


def run_web_only() -> None:
    import logging
    import threading

    from bot import Bot
    from config import AppConfig
    from i18n import set_language
    from logsetup import LogBuffer, setup_logging
    from supervisor import AutoRestart
    from web import WebDashboard, running_instance

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # emojis in the console log
    except (AttributeError, ValueError):
        pass
    cfg = AppConfig()
    set_language(cfg.get("app", "language", "es"))
    where = running_instance(cfg)
    if where:
        print(f"Ya hay un Airline Manager 4 Bot de este perfil en marcha: http://{where}:{cfg.get_int('web', 'port', 8744)}/")
        sys.exit(0)
    buffer = LogBuffer()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("[%(asctime)s] [%(tag)s] %(message)s", "%H:%M:%S"))
    setup_logging(cfg, buffer, console)
    bot = Bot(cfg)
    restart = AutoRestart()
    quit_requested = threading.Event()
    web = WebDashboard(bot, cfg, buffer, lambda: restart.restart_in, on_quit=quit_requested.set)
    if not web.start():
        sys.exit(1)
    if cfg.get_bool("options", "start_on_launch"):
        bot.start()
    try:
        while not quit_requested.wait(1):
            if restart.tick(bot.is_alive(), bot.state, cfg.get_bool("options", "auto_restart", True)):
                bot.start()
    except KeyboardInterrupt:
        pass
    # Stop cleanly so that Chrome and chromedriver are closed too.
    bot.stop()
    bot.join(timeout=20)
    if bot.is_alive():
        bot.kill_browser()
    web.stop()


def select_profile(args: list[str]) -> None:
    """--profile <name> / --profile=<name>: activate it, creating it from the main settings if it is new."""
    import paths

    name = ""
    for index, arg in enumerate(args):
        if arg == "--profile" and index + 1 < len(args):
            name = args[index + 1]
        elif arg.startswith("--profile="):
            name = arg.split("=", 1)[1]
    if name and paths.normalize(name) != paths.MAIN_LABEL and not paths.valid_name(paths.normalize(name)):
        print(f"Nombre de perfil no válido: «{name}» (letras, números, - y _; hasta 24).")
        sys.exit(2)
    profile = paths.activate(name)
    if not profile.exists():
        paths.create(profile.name)
        print(f"Perfil «{profile.label}» creado en {profile.root} (panel web en el puerto {profile.port()}).")


def main() -> None:
    # Config, assets and logs are addressed relative to the project root.
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "src"))
    select_profile(sys.argv[1:])
    if "--web" in sys.argv[1:]:
        run_web_only()
    else:
        run_desktop()


if __name__ == "__main__":
    main()
