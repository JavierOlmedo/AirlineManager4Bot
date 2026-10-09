"""Logging for the desktop app and web mode: the rotating log file plus an in-memory buffer for the web page."""
from __future__ import annotations

import collections
import logging
import logging.handlers
import threading
from pathlib import Path

import paths
from config import AppConfig
from helpers import LEVEL_STYLES, TagFilter, log_tag

LOG_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"


class LogBuffer(logging.Handler):
    """Keeps the last log lines (INFO and up) as dicts, numbered, so the web page can ask for the new ones."""

    def __init__(self, size: int = 600):
        super().__init__(logging.INFO)
        self._lines: collections.deque = collections.deque(maxlen=size)
        self._next_id = 1
        self._lock_lines = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level_label, level_emoji, level_colour = LEVEL_STYLES.get(record.levelname, LEVEL_STYLES["INFO"])
            tag_label, tag_emoji, tag_colour = log_tag(record.name)
            line = {
                "time": record.created,
                "level": level_label,
                "level_key": record.levelname,
                "level_colour": level_colour,
                "tag": tag_label,
                "tag_colour": tag_colour,
                "emoji": level_emoji or tag_emoji,
                "message": record.getMessage(),
            }
        except Exception:  # noqa: BLE001 - a broken log call must never break the bot
            return
        with self._lock_lines:
            line["id"] = self._next_id
            self._next_id += 1
            self._lines.append(line)

    def since(self, last_id: int) -> list[dict]:
        with self._lock_lines:
            return [line for line in self._lines if line["id"] > last_id]


def setup_logging(cfg: AppConfig, *handlers: logging.Handler) -> Path:
    """Attach the file log and the given handlers (INFO and up) to the 'am4bot' logger. Returns the log file path."""
    logger = logging.getLogger("am4bot")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    tag_filter = TagFilter()
    for handler in handlers:
        if handler.level == logging.NOTSET:
            handler.setLevel(logging.INFO)
        handler.addFilter(tag_filter)
        logger.addHandler(handler)

    # "data/..." means the data folder of the active profile (see paths.py)
    log_file = paths.data_path(Path(cfg.get("app", "log_file", "data/logs/am4bot.log")))
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError:  # an old plain file named "logs" is in the way
        log_file = paths.current().data / log_file.name
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(tag)s] %(message)s", LOG_DATE_FORMAT))
    file_handler.addFilter(tag_filter)
    logger.addHandler(file_handler)

    logging.getLogger("selenium").setLevel(logging.WARNING)
    return log_file
