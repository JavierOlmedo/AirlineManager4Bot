"""Thread-safe access to the two config files.

* ``config/settings.ini``  - tracked in git, never contains secrets.
* ``config/secrets.ini``   - git-ignored, holds the game credentials.

The GUI is the only writer. The bot thread only reads, so a single re-entrant
lock around the parsers is enough.
"""
from __future__ import annotations

import threading
from configparser import ConfigParser
from pathlib import Path

SETTINGS_FILE = Path("config/settings.ini")
SECRETS_FILE = Path("config/secrets.ini")


class AppConfig:
    def __init__(self, settings_file: Path = SETTINGS_FILE, secrets_file: Path = SECRETS_FILE):
        self._lock = threading.RLock()
        self.settings_file = Path(settings_file)
        self.secrets_file = Path(secrets_file)
        self._settings = ConfigParser(interpolation=None)
        self._secrets = ConfigParser(interpolation=None)
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self._settings.read(self.settings_file, encoding="utf-8")
            self._secrets.read(self.secrets_file, encoding="utf-8")  # a missing file is fine

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
            self._settings.set(section, key, str(value))

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

    def forget_credentials(self) -> bool:
        """Delete secrets.ini from disk (the in-memory copy is kept for the current run)."""
        with self._lock:
            if self.secrets_file.exists():
                self.secrets_file.unlink()
                return True
            return False
