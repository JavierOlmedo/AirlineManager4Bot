"""Thread-safe access to the config files of the active profile (see paths.py).

* ``config/defaults.ini`` - tracked in git and shared by every profile: every setting with its default value,
  plus the page selectors (those are code, so they always come from this file).
* ``settings.ini``        - git-ignored, one per profile (main: config/settings.ini): only what the user changed.
  Values equal to the default are left out, so a new default reaches everybody who never touched it.
* ``secrets.ini``         - git-ignored, holds the game credentials, the Telegram token and the web token.

The desktop window and the web dashboard write, the bot thread only reads, so a single
re-entrant lock around the parsers is enough. ``version`` grows with every change, so one
interface can notice (and show) what the other one changed.
"""
from __future__ import annotations

import threading
from configparser import ConfigParser
from pathlib import Path
from typing import Optional

import paths

# Sections that only defaults.ini may set: an old full copy of settings.ini must not pin outdated selectors.
CODE_SECTIONS = ("selectors",)
SETTINGS_HEADER = ("; Your settings: only what differs from config/defaults.ini (every option is there, explained in the\n"
                   "; README). Change them in the app or the web dashboard, or here while the bot is closed.\n\n")


def _parser() -> ConfigParser:
    return ConfigParser(interpolation=None)


class AppConfig:
    def __init__(self, settings_file: Optional[Path] = None, secrets_file: Optional[Path] = None,
                 defaults_file: Optional[Path] = None):
        self._lock = threading.RLock()
        self.profile = paths.current()
        self.defaults_file = Path(defaults_file or paths.DEFAULTS_FILE)
        self.settings_file = Path(settings_file or self.profile.settings)
        self.secrets_file = Path(secrets_file or self.profile.secrets)
        self._defaults = _parser()
        self._settings = _parser()
        self._secrets = _parser()
        self.version = 0
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._defaults.read(self.defaults_file, encoding="utf-8")
            self._settings.read(self.settings_file, encoding="utf-8")
            for section in CODE_SECTIONS:
                self._settings.remove_section(section)
            self._secrets.read(self.secrets_file, encoding="utf-8")  # a missing file is fine
            paths.make_private(self.secrets_file)

    def reload_secrets(self) -> None:
        """Pick up edits made to secrets.ini by hand (for example a new Telegram token)."""
        with self._lock:
            if self.secrets_file.exists():
                self._secrets.read(self.secrets_file, encoding="utf-8")

    # ------------------------------------------------------------------ readers
    def _raw(self, section: str, key: str) -> Optional[str]:
        for parser in (self._settings, self._defaults):
            if parser.has_option(section, key):
                return parser.get(section, key)
        return None

    def get(self, section: str, key: str, fallback: str = "") -> str:
        with self._lock:
            value = self._raw(section, key)
            return (fallback if value is None else value).strip()

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        with self._lock:
            value = self._raw(section, key)
            try:
                return fallback if value is None else int(value)
            except ValueError:
                return fallback

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        with self._lock:
            value = self._raw(section, key)
            if value is None:
                return fallback
            return ConfigParser.BOOLEAN_STATES.get(value.strip().lower(), fallback)

    # ------------------------------------------------------------------ writers
    def set(self, section: str, key: str, value: object) -> None:
        value = str(value)
        with self._lock:
            if self._raw(section, key) == value:
                return
            default = self._defaults.get(section, key, fallback=None)
            if default is not None and default.strip() == value.strip():
                if self._settings.has_option(section, key):
                    self._settings.remove_option(section, key)
            else:
                if not self._settings.has_section(section):
                    self._settings.add_section(section)
                self._settings.set(section, key, value)
            self.version += 1

    def save(self) -> None:
        with self._lock:
            # Drop what equals the default (also tidies an old full copy of the settings on its first save).
            for section in self._settings.sections():
                for key, value in list(self._settings.items(section, raw=True)):
                    default = self._defaults.get(section, key, fallback=None)
                    if default is not None and default.strip() == value.strip():
                        self._settings.remove_option(section, key)
                if not self._settings.options(section):
                    self._settings.remove_section(section)
            paths.write_atomic(self.settings_file, paths.ini_text(self._settings, SETTINGS_HEADER))

    # ------------------------------------------------------------------ secrets
    @property
    def credentials(self) -> tuple[str, str]:
        with self._lock:
            return (
                self._secrets.get("login", "username", fallback="").strip(),
                self._secrets.get("login", "password", fallback=""),
            )

    def set_credentials(self, username: str, password: str, persist: bool) -> None:
        """Keep credentials for this run; write them to secrets.ini only when *persist* is true."""
        with self._lock:
            if not self._secrets.has_section("login"):
                self._secrets.add_section("login")
            self._secrets.set("login", "username", username)
            self._secrets.set("login", "password", password)
            if persist:
                paths.write_atomic(self.secrets_file, paths.ini_text(self._secrets), private=True)

    @property
    def web_token(self) -> str:
        """Access token of the web dashboard ([web] token in secrets.ini); empty = no token."""
        with self._lock:
            return self._secrets.get("web", "token", fallback="").strip()

    @property
    def telegram(self) -> tuple[str, str]:
        """(bot token, chat id) from the [telegram] section of secrets.ini, empty strings when unset."""
        with self._lock:
            return (
                self._secrets.get("telegram", "bot_token", fallback="").strip(),
                self._secrets.get("telegram", "chat_id", fallback="").strip(),
            )

    def forget_credentials(self) -> bool:
        """Remove the game login from secrets.ini on disk; the Telegram and web tokens stay.
        The in-memory copy is kept for the current run."""
        with self._lock:
            if not self.secrets_file.exists():
                return False
            disk = _parser()
            disk.read(self.secrets_file, encoding="utf-8")
            if not disk.remove_section("login"):
                return False
            if disk.sections():
                paths.write_atomic(self.secrets_file, paths.ini_text(disk), private=True)
            else:
                self.secrets_file.unlink()
            return True
