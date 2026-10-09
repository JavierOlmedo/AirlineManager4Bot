"""Telegram notifications through the Bot API, with the standard library only.

Messages are queued and sent from a background thread so the bot never waits
for the network. Failures are logged at most once every 10 minutes.

Set-up: create a bot with @BotFather (you get the token), send it any message,
then open https://api.telegram.org/bot<TOKEN>/getUpdates to read your chat id.
Both values go to config/secrets.ini under [telegram].
"""
from __future__ import annotations

import html
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("am4bot.telegram")

API_URL = "https://api.telegram.org/bot{token}/{method}"
MAX_LENGTH = 4000  # Telegram allows 4096 characters per message


def esc(value: object) -> str:
    """Escape dynamic text for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)


class Telegram:
    def __init__(self, token: str = "", chat_id: str = ""):
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()
        self._queue: "queue.Queue[tuple[str, bool]]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._last_failure = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    # ------------------------------------------------------------------ public API
    def send(self, text: str, silent: bool = False) -> None:
        """Queue a message (HTML parse mode). No-op when the token or chat id is missing."""
        if not self.enabled:
            return
        self._queue.put((text, silent))
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(target=self._run, name="telegram", daemon=True)
            self._worker.start()

    def send_now(self, text: str) -> tuple[bool, str]:
        """Send synchronously and return (ok, description). Used by the GUI test button."""
        if not self.enabled:
            return False, "token or chat id missing in config/secrets.ini"
        return self._post(text, silent=False)

    # ------------------------------------------------------------------ internals
    def _run(self) -> None:
        while True:
            text, silent = self._queue.get()
            ok, description = self._post(text, silent)
            if not ok and time.time() - self._last_failure > 600:
                log.warning("Telegram message failed: %s", description)
                self._last_failure = time.time()
            self._queue.task_done()

    def _post(self, text: str, silent: bool) -> tuple[bool, str]:
        payload = urllib.parse.urlencode({
            "chat_id": self.chat_id,
            "text": text[:MAX_LENGTH],
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
            "disable_notification": "true" if silent else "false",
        }).encode()
        request = urllib.request.Request(API_URL.format(token=self.token, method="sendMessage"), data=payload)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode("utf-8", "replace"))
            except ValueError:
                body = {}
            return False, body.get("description") or f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, str(exc)
        if body.get("ok"):
            return True, "sent"
        return False, body.get("description") or "unknown error"


if __name__ == "__main__":  # quick manual check: python src/notify.py
    import os
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root / "src"))
    from config import AppConfig

    token, chat_id = AppConfig().telegram
    client = Telegram(token, chat_id)
    print("configured:", client.enabled)
    if client.enabled:
        print(client.send_now("✅ <b>Airline Manager 4 Bot</b> conectado a Telegram."))
