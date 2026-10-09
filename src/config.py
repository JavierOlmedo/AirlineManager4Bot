"""Thread-safe access to the two config files of the active profile (see paths.py).

* ``settings.ini``  - main profile: config/settings.ini, tracked in git, never contains secrets.
* ``secrets.ini``   - git-ignored, holds the game credentials, the Telegram token and the web token.

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


class AppConfig:
    def __init__(self, settings_file: Optional[Path] = None, secrets_file: Optional[Path] = None):
        self._lock = threading.RLock()
        self.profile = paths.current()
        self.settings_file = Path(settings_file or self.profile.settings)
        self.secrets_file = Path(secrets_file or self.profile.secrets)
        self._settings = ConfigParser(interpolation=None)
        self._secrets = ConfigParser(interpolation=None)
        self.version = 0
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._settings.read(self.settings_file, encoding="utf-8")
            self._secrets.read(self.secrets_file, encoding="utf-8")  # a missing file is fine

    def reload_secrets(self) -> None:
        """Pick up edits made to secrets.ini by hand (for example a new Telegram token)."""
        with self._lock:
            if self.secrets_file.exists():
                self._secrets.read(self.secrets_file, encoding="utf-8")

    # ------------------------------------------------------------------ readers
    def get(self, section: str, key: str, fallback: str = "") -> str:
        with self._lock:
            return self._settings.get(section, key, fallback=fallback).strip()

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        with self._lock:
            try:
                return self._settings.getint(section, key, fallback=fallback)
            except ValueError:
                return fallback

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        with self._lock:
            try:
                return self._settings.getboolean(section, key, fallback=fallback)
            except ValueError:
                return fallback

    # ------------------------------------------------------------------ writers
    def set(self, section: str, key: str, value: object) -> None:
        with self._lock:
            if not self._settings.has_section(section):
                self._settings.add_section(section)
            if self._settings.get(section, key, fallback=None) != str(value):
                self._settings.set(section, key, str(value))
                self.version += 1

    def save(self) -> None:
        with self._lock:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with self.settings_file.open("w", encoding="utf-8") as handle:
                self._settings.write(handle)

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
                self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
                with self.secrets_file.open("w", encoding="utf-8") as handle:
                    self._secrets.write(handle)

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
        """Delete secrets.ini from disk (the in-memory copy is kept for the current run)."""
        with self._lock:
            if self.secrets_file.exists():
                self.secrets_file.unlink()
                return True
            return False
