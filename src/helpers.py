"""Small parsing helpers shared by the bot modules."""
from __future__ import annotations

import re
from typing import Optional

_TIMER_RE = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})")


def to_int(text: Optional[str]) -> Optional[int]:
    """'$ 2,520,974' -> 2520974. None when there are no digits."""
    if text is None:
        return None
    digits = re.sub(r"\D", "", str(text))
    return int(digits) if digits else None


def first_int(pattern: re.Pattern[str], text: str, group: int = 1) -> Optional[int]:
    match = pattern.search(text or "")
    return to_int(match.group(group)) if match else None


def timer_seconds(text: Optional[str]) -> Optional[int]:
    """'00:19:44' -> 1184 seconds."""
    match = _TIMER_RE.search(text or "")
    if not match:
        return None
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def fmt_duration(seconds: int) -> str:
    """125 -> '02:05', 20367 -> '5:39 h' (realism flights take hours)."""
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d} h"
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fmt(value: Optional[int]) -> str:
    return f"{value:,}" if isinstance(value, int) else "?"


def clean_response(text: str, limit: int = 120) -> str:
    """Trim a game Ajax response for the log; drops it when it is only JavaScript."""
    text = " ".join((text or "").split())
    if not text or ("(" in text and ";" in text) or "$(" in text:
        return ""
    return text[:limit]


# Log categories: logger suffix -> (label shown in the log, emoji, colour)
LOG_TAGS = {
    "bot": ("BOT", "🤖", "#95a5a6"),
    "app": ("APP", "🖥️", "#7f8c8d"),
    "login": ("LOGIN", "🔑", "#bdc3c7"),
    "dinero": ("DINERO", "💰", "#f1c40f"),
    "vuelos": ("VUELOS", "✈️", "#5dade2"),
    "fuel": ("FUEL", "⛽", "#f39c12"),
    "co2": ("CO2", "🌿", "#2ecc71"),
    "mant": ("MANT", "🔧", "#1abc9c"),
    "flota": ("FLOTA", "🛩️", "#3498db"),
    "rutas": ("RUTAS", "🛫", "#9b59b6"),
    "aviones": ("AVIONES", "🛒", "#e67e22"),
    "marketing": ("MARKETING", "📣", "#ff7675"),
    "asientos": ("ASIENTOS", "💺", "#fd79a8"),
    "checklist": ("CHECKLIST", "📋", "#00b894"),
    "telegram": ("TELEGRAM", "📨", "#29a9eb"),
}
LEVEL_STYLES = {
    "DEBUG": ("DEBUG", "", "#7f8c8d"),
    "INFO": ("INFO", "", "#4da3ff"),
    "WARNING": ("AVISO", "⚠️", "#f5a623"),
    "ERROR": ("ERROR", "❌", "#e74c3c"),
    "CRITICAL": ("ERROR", "❌", "#e74c3c"),
}


def log_tag(logger_name: str) -> tuple[str, str, str]:
    """(label, emoji, colour) for a logger such as 'am4bot.fuel'."""
    suffix = logger_name.rsplit(".", 1)[-1] if "." in logger_name else "bot"
    return LOG_TAGS.get(suffix, LOG_TAGS["bot"])


class TagFilter:
    """logging filter that adds record.tag / record.emoji so formatters can print [TAG]."""

    def filter(self, record) -> bool:  # noqa: D401 - logging API
        label, emoji, _colour = log_tag(record.name)
        record.tag = label
        record.emoji = emoji
        return True
