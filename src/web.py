"""Web dashboard: the same statistics, log, controls and settings as the desktop window, in a browser.

A small stdlib HTTP server (no extra dependencies) runs in a daemon thread next to the bot. It serves
assets/web/index.html and a JSON API:

* GET  /api/status            snapshot of the dashboard (dashboard.snapshot) + last log id
* GET  /api/log?since=<id>    new log lines
* GET  /api/settings          tabs with their fields / switches, current values and help texts
* POST /api/settings          {"settings": {key: int}, "options": {key: bool}, "text": {key: str}}
* POST /api/control           {"action": "start" | "stop" | "run_now" | "quit"}  (quit: stop the bot and close
                              the program; used by scripts/web_parar.ps1)

Safety: by default it only listens on 127.0.0.1. To open it to the local network ([web] host = 0.0.0.0)
a token is required ([web] token in config/secrets.ini); without one the server stays on 127.0.0.1.
POSTs need the X-AM4 header (a cross-site page cannot send it) and, without a token, only local Host
names are accepted (no DNS rebinding). Credentials and Telegram secrets are never sent to the page.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
import socket
import threading
import urllib.request
from configparser import ConfigParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional
from urllib.parse import parse_qs, urlparse

import paths
from dashboard import snapshot
from economy import AUTO_GOAL_LABEL, is_auto_goal, load_market, load_state
from i18n import language, t, tip
from settings_schema import ALL_FIELDS, ALL_SWITCHES, OPTION_DEFAULTS, TABS, TEXT_SETTINGS, clamp_settings, parse_int

if TYPE_CHECKING:
    from bot import Bot
    from config import AppConfig
    from logsetup import LogBuffer

log = logging.getLogger("am4bot.app")

PAGE = Path("assets/web/index.html")
COOKIE = "am4token"
MAX_BODY = 64 * 1024


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


class _ExclusiveServer(ThreadingHTTPServer):
    """The port belongs to one program only. On Windows SO_REUSEADDR (http.server's default) lets a second
    program bind a port that is already listening, so a second bot would not notice the first one."""

    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_bind(self) -> None:
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def instance_answers(port: int, token: str = "", host: str = "127.0.0.1") -> bool:
    """True when a copy of the bot (desktop app or web mode) answers on this dashboard port."""
    request = urllib.request.Request(f"http://{host}:{port}/api/status", headers={"X-Token": token})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a system proxy
    try:
        with opener.open(request, timeout=1.5) as response:
            return "state_key" in json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def other_hosts(cfg: "AppConfig") -> list[str]:
    """[web] remote_instances: other machines that may run the same profiles (for example the Raspberry)."""
    return [host.strip() for host in cfg.get("web", "remote_instances", "").split(",") if host.strip()]


def running_instance(cfg: "AppConfig", include_local: bool = True) -> Optional[str]:
    """Where another copy of this profile's bot already runs ("127.0.0.1" or a remote host), else None.
    Two copies would fight over the same airline (and, on one machine, the same Chrome profile), so the
    second one must not start its bot. *include_local* False skips this machine (our own dashboard)."""
    port, token = cfg.get_int("web", "port", 8744), cfg.web_token
    for host in (["127.0.0.1"] if include_local else []) + other_hosts(cfg):
        if instance_answers(port, token, host):
            return host
    return None


def profile_token(profile: paths.Profile) -> str:
    parser = ConfigParser(interpolation=None)
    parser.read(profile.secrets, encoding="utf-8")
    return parser.get("web", "token", fallback="").strip()


def profile_running(profile: paths.Profile) -> bool:
    return instance_answers(profile.port(), profile_token(profile))


class WebDashboard:
    def __init__(self, bot: "Bot", cfg: "AppConfig", buffer: "LogBuffer",
                 restart_in: Callable[[], Optional[int]] = lambda: None,
                 start_bot: Optional[Callable[[], None]] = None,
                 on_quit: Optional[Callable[[], None]] = None):
        self.bot = bot
        self.cfg = cfg
        self.buffer = buffer
        self.restart_in = restart_in
        self.start_bot = start_bot or bot.start
        self.on_quit = on_quit
        self.server: Optional[ThreadingHTTPServer] = None
        self.url = ""

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        host = self.cfg.get("web", "host", "127.0.0.1") or "127.0.0.1"
        port = self.cfg.get_int("web", "port", 8744)
        if not _is_loopback(host) and not self.cfg.web_token:
            log.warning("Web: para abrirla a la red local hace falta [web] token en config/secrets.ini; "
                        "de momento solo escucha en 127.0.0.1.")
            host = "127.0.0.1"
        try:
            self.server = _ExclusiveServer((host, port), self._handler())
        except OSError as exc:
            if running_instance(self.cfg):
                log.warning("Ya hay otro Airline Manager 4 Bot en marcha (panel web en http://127.0.0.1:%s/).", port)
            else:
                log.warning("Web: no puedo abrir el puerto %s (%s).", port, exc.strerror or exc)
            return False
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, name="am4web", daemon=True).start()
        shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        self.url = f"http://{shown}:{port}/"
        log.info("Panel web en %s%s", self.url, " (también desde la red local, con token)" if not _is_loopback(host) else "")
        return True

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    # ------------------------------------------------------------------ data
    def status(self) -> dict:
        data = snapshot(self.bot, self.cfg, load_state(), load_market(), self.restart_in())
        data["profile"] = None if self.cfg.profile.is_main else self.cfg.profile.label
        lines = self.buffer.since(0)
        data["log_last"] = lines[-1]["id"] if lines else 0
        return data

    def settings(self) -> dict:
        cfg = self.cfg
        tabs = []
        for name, icon, fields, switches in TABS:
            tabs.append({
                "key": name, "name": t(name), "icon": icon,
                "fields": [{"key": k, "label": t(label), "value": cfg.get_int("settings", k), "help": tip(k) or ""}
                           for k, label in fields],
                "switches": [{"key": k, "label": t(label), "help": tip(k) or "",
                              "value": cfg.get_bool("options", k, OPTION_DEFAULTS.get(k, False))}
                             for k, label in switches],
            })
        goal = cfg.get("settings", "goal_model")
        models = sorted((m for m in load_market() if m.get("capacity", 0) >= 100), key=lambda m: -m.get("price", 0))
        text = [{"key": k, "label": t(label), "help": tip(k) or "",
                 "value": t(AUTO_GOAL_LABEL) if k == "goal_model" and is_auto_goal(goal) else cfg.get("settings", k)}
                for k, label in TEXT_SETTINGS]
        return {"tabs": tabs, "text": text, "goal_options": [t(AUTO_GOAL_LABEL)] + [m["name"] for m in models],
                "lang": language()}

    def update_settings(self, payload: dict) -> tuple[bool, str]:
        known_fields = {k for k, _ in ALL_FIELDS}
        known_switches = {k for k, _ in ALL_SWITCHES}
        numbers: dict[str, int] = {}
        for key, raw in (payload.get("settings") or {}).items():
            value = parse_int(raw)
            if key not in known_fields or value is None:
                return False, t("«{key}» debe ser un número entero.", key=key)
            numbers[key] = value
        options = payload.get("options") or {}
        texts = payload.get("text") or {}
        unknown = [k for k in options if k not in known_switches] + [k for k in texts if k not in dict(TEXT_SETTINGS)]
        if unknown:
            return False, t("Ajuste desconocido «{key}».", key=unknown[0])
        if numbers:
            current = {k: self.cfg.get_int("settings", k) for k in ("cycle_min_minutes", "cycle_max_minutes")}
            numbers = clamp_settings({**current, **numbers})
        for key, value in numbers.items():
            self.cfg.set("settings", key, value)
        for key, value in options.items():
            self.cfg.set("options", key, "on" if value else "off")
            if key in ("auto_marketing", "marketing_eco"):
                self.bot.marketing_next_check = 0.0
        for key, value in texts.items():
            value = str(value).strip()[:80]
            self.cfg.set("settings", key, "auto" if key == "goal_model" and is_auto_goal(value) else value)
        self.cfg.save()
        log.info("Ajustes guardados desde el panel web.")
        return True, t("Guardado.")

    def control(self, action: str) -> tuple[bool, str]:
        if action == "start":
            if self.bot.is_alive():
                return False, t("El bot ya está en marcha.")
            self.start_bot()
            return True, t("Iniciando el bot ...")
        if action == "stop":
            if not self.bot.is_alive():
                return False, t("El bot ya está parado.")
            log.info("Parando tras el paso actual (desde el panel web) ...")
            self.bot.stop()
            return True, t("Parando ...")
        if action == "run_now":
            self.bot.run_now()
            return True, t("Revisando ahora.")
        if action == "quit" and self.on_quit is not None:
            log.info("Cerrando el programa (pedido desde el panel web) ...")
            self.on_quit()
            return True, t("Cerrando ...")
        return False, t("Acción desconocida.")

    # ------------------------------------------------------------------ HTTP
    def _handler(self):
        dashboard = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AM4Bot"

            def log_message(self, *_args) -> None:  # keep HTTP noise out of the bot log
                pass

            # -- access control
            def _allowed(self) -> bool:
                token = dashboard.cfg.web_token
                if token:
                    query = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                    cookies = dict(part.strip().split("=", 1) for part in (self.headers.get("Cookie") or "").split(";")
                                   if "=" in part)
                    given = query or cookies.get(COOKIE, "") or self.headers.get("X-Token", "")
                    return hmac.compare_digest(given.encode(), token.encode())
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return _is_loopback(host)

            def _send(self, status: int, body: bytes, content_type: str, extra: Optional[dict] = None) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                for key, value in (extra or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, data, status: int = 200) -> None:
                self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _deny(self) -> None:
                self._send(HTTPStatus.FORBIDDEN, "Acceso denegado: abre la página con ?token=...".encode("utf-8"),
                           "text/plain; charset=utf-8")

            def do_GET(self) -> None:  # noqa: N802 - http.server API
                if not self._allowed():
                    return self._deny()
                url = urlparse(self.path)
                if url.path in ("/", "/index.html"):
                    extra = {}
                    token = dashboard.cfg.web_token
                    if token:
                        extra["Set-Cookie"] = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000"
                    try:
                        body = PAGE.read_bytes()
                    except OSError:
                        return self._send(HTTPStatus.NOT_FOUND, b"assets/web/index.html not found", "text/plain")
                    return self._send(200, body, "text/html; charset=utf-8", extra)
                if url.path == "/api/status":
                    return self._json(dashboard.status())
                if url.path == "/api/log":
                    since = parse_int(parse_qs(url.query).get("since", ["0"])[0]) or 0
                    return self._json({"lines": dashboard.buffer.since(since)})
                if url.path == "/api/settings":
                    return self._json(dashboard.settings())
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")

            def do_POST(self) -> None:  # noqa: N802 - http.server API
                if not self._allowed() or self.headers.get("X-AM4") != "1":
                    return self._deny()
                length = parse_int(self.headers.get("Content-Length", "0")) or 0
                if length > MAX_BODY:
                    return self._json({"ok": False, "message": "Petición demasiado grande."}, 413)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except ValueError:
                    return self._json({"ok": False, "message": "JSON no válido."}, 400)
                if not isinstance(payload, dict):
                    return self._json({"ok": False, "message": "JSON no válido."}, 400)
                path = urlparse(self.path).path
                if path == "/api/settings":
                    ok, message = dashboard.update_settings(payload)
                elif path == "/api/control":
                    ok, message = dashboard.control(str(payload.get("action", "")))
                else:
                    return self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
                self._json({"ok": ok, "message": message}, 200 if ok else 400)

        return Handler
