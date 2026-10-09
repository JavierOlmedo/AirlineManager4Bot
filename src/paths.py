"""Profiles: one set of files per game account, so several airlines can run side by side.

The main profile keeps the original layout:
    config/settings.ini, config/secrets.ini, config/session/ (Chrome), data/ (state, prices, market, logs)
A named profile keeps everything in its own git-ignored folder:
    profiles/<name>/settings.ini, secrets.ini, session/, data/
Every settings.ini only holds what differs from config/defaults.ini (tracked in git, shared by all profiles).

A process runs one profile, chosen at start (``main.py --profile <name>``) with ``activate()``; every
module asks ``current()`` when it needs a path. Each profile has its own web dashboard port, so two
profiles can run at the same time without sharing Chrome, data or settings.
"""
from __future__ import annotations

import io
import os
import re
import time
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

MAIN_LABEL = "principal"
PROFILES_DIR = Path("profiles")
DEFAULTS_FILE = Path("config/defaults.ini")
FIRST_PORT = 8744
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,23}$")


@dataclass(frozen=True)
class Profile:
    name: str  # "" = the main profile

    @property
    def is_main(self) -> bool:
        return not self.name

    @property
    def label(self) -> str:
        return self.name or MAIN_LABEL

    @property
    def root(self) -> Path:
        return Path("config") if self.is_main else PROFILES_DIR / self.name

    @property
    def settings(self) -> Path:
        return self.root / "settings.ini"

    @property
    def secrets(self) -> Path:
        return self.root / "secrets.ini"

    @property
    def session(self) -> Path:
        return self.root / "session"

    @property
    def data(self) -> Path:
        return Path("data") if self.is_main else self.root / "data"

    def exists(self) -> bool:
        return self.is_main or self.settings.exists()

    def port(self) -> int:
        parser = ConfigParser(interpolation=None)
        parser.read([DEFAULTS_FILE, self.settings], encoding="utf-8")
        try:
            return parser.getint("web", "port", fallback=FIRST_PORT)
        except ValueError:
            return FIRST_PORT


_current = Profile("")


def current() -> Profile:
    return _current


def activate(name: Optional[str]) -> Profile:
    """Select the profile of this process (None, "" or "principal" = the main one)."""
    global _current
    name = normalize(name or "")
    _current = Profile("" if name in ("", MAIN_LABEL) else name)
    return _current


def normalize(name: str) -> str:
    return re.sub(r"\s+", "-", name.strip().lower())


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name)) and name != MAIN_LABEL


def all_profiles() -> list[Profile]:
    named = sorted(d.name for d in PROFILES_DIR.iterdir() if (d / "settings.ini").exists()) if PROFILES_DIR.is_dir() else []
    return [Profile("")] + [Profile(name) for name in named if valid_name(name)]


def data_path(path: Path) -> Path:
    """'data/logs/x.log' -> the current profile's data folder; any other path is left as it is."""
    path = Path(path)
    if not path.is_absolute() and path.parts and path.parts[0] == "data":
        return current().data.joinpath(*path.parts[1:])
    return path


def write_atomic(path: Path, text: str, private: bool = False) -> None:
    """Write *text* through a temporary file in the same folder, so a crash or another thread never sees half a
    file. *private* (secrets) keeps it readable by its owner only (0600; Windows has its own ACLs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        # O_BINARY: on Windows a text-mode descriptor would turn the "\r\n" of the text layer into "\r\r\n".
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
        with open(os.open(temp, flags, 0o600 if private else 0o666), "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if private:
            make_private(temp)
        for attempt in range(5):
            try:
                os.replace(temp, path)
                break
            except PermissionError:  # Windows: another thread is reading the old file right now
                if attempt == 4:
                    raise
                time.sleep(0.1)
    finally:
        if temp.exists():
            temp.unlink()


def make_private(path: Path) -> None:
    """Owner-only permissions on a secrets file (no-op on Windows or when it does not exist)."""
    if os.name != "nt" and Path(path).exists():
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def ini_text(parser: ConfigParser, header: str = "") -> str:
    buffer = io.StringIO()
    buffer.write(header)
    parser.write(buffer)
    return buffer.getvalue()


def create(name: str, source: Optional[Profile] = None) -> Profile:
    """New profile with the settings of *source* (the main one by default), its own web port, start on
    launch off (the account is typed in first) and only the Telegram part of the secrets (same chat)."""
    name = normalize(name)
    if not valid_name(name):
        raise ValueError(f"Nombre de perfil no válido: «{name}» (letras, números, - y _; hasta 24).")
    profile = Profile(name)
    if profile.exists():
        raise ValueError(f"El perfil «{name}» ya existe.")
    source = source or Profile("")
    settings = ConfigParser(interpolation=None)
    settings.read(source.settings, encoding="utf-8")
    settings.remove_section("selectors")  # always taken from config/defaults.ini
    for section in ("web", "options"):
        if not settings.has_section(section):
            settings.add_section(section)
    settings.set("web", "port", str(max(p.port() for p in all_profiles()) + 1))
    settings.set("options", "start_on_launch", "off")
    profile.root.mkdir(parents=True, exist_ok=True)
    profile.data.mkdir(parents=True, exist_ok=True)
    write_atomic(profile.settings, ini_text(settings))
    secrets = ConfigParser(interpolation=None)
    secrets.read(source.secrets, encoding="utf-8")
    copy = ConfigParser(interpolation=None)
    if secrets.has_section("telegram"):
        copy.add_section("telegram")
        for key, value in secrets.items("telegram"):
            copy.set("telegram", key, value)
    write_atomic(profile.secrets, ini_text(copy), private=True)
    return profile
