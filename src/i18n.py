"""Interface language of the desktop window and the web dashboard: Spanish (source) or English.

The Spanish text is the key: ``t("Guardar ajustes")`` returns it as is in Spanish and the English entry of
``EN`` in English, so the code keeps reading naturally. Texts with placeholders use ``str.format`` names:
``t("Próxima revisión en {time}", time="02:05")``. Help texts live in help_texts.py (``tip(key)``).
The log and the Telegram messages are still Spanish only.
"""
from __future__ import annotations

LANGUAGES = {"es": "Español", "en": "English"}
DEFAULT_LANGUAGE = "en"  # until [app] language is chosen in the sidebar
_language = DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    global _language
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _language


def language() -> str:
    return _language


def t(text: str, **values) -> str:
    result = EN.get(text, text) if _language == "en" else text
    return result.format(**values) if values else result


def tip(key: str):
    """Hover help of a setting or control in the current language (None if there is none)."""
    from help_texts import HELP, HELP_EN
    return (HELP_EN if _language == "en" else HELP).get(key) or HELP.get(key)


EN: dict[str, str] = {
    # ---- settings (settings_schema.py) and tabs
    "Mercado": "Market", "Flota": "Fleet", "Aviones": "Aircraft", "Opciones": "Options",
    "Comprar fuel a ≤ $": "Buy fuel at ≤ $", "Comprar CO2 a ≤ $": "Buy CO2 at ≤ $",
    "Stock mínimo (%)": "Minimum stock (%)", "Stock máx. (días)": "Max. stock (days)",
    "Gasto máx. (% caja)": "Max. spend (% of cash)",
    "Espera mín. (min)": "Min. wait (min)", "Espera máx. (min)": "Max. wait (min)",
    "Percentil compra (%)": "Buy percentile (%)", "Percentil excepc. (%)": "Exceptional pctl. (%)",
    "Histórico (días)": "History (days)", "Máx. fuel / compra": "Max. fuel / purchase",
    "Máx. CO2 / compra": "Max. CO2 / purchase",
    "Reparar a partir de desgaste (%)": "Repair from wear (%)", "A-check si quedan <= horas": "A-check at <= hours left",
    "Reserva de caja ($)": "Cash reserve ($)", "Ruta máx. avión pequeño (km)": "Max. route, small aircraft (km)",
    "Ruta máx. avión grande (km)": "Max. route, big aircraft (km)", "Pista mínima (ft)": "Minimum runway (ft)",
    "Huecos libres en el hangar": "Free hangar slots", "Rutas / pedidos por ciclo": "Routes / orders per cycle",
    "Taller: amortizar en ≤ días": "Workshop: pay back in ≤ days",
    "Mejoras de avión: velocidad, fuel y CO2": "Aircraft upgrades: speed, fuel and CO2",
    "Precio máx. sin objetivo (0 = libre)": "Max. price without goal (0 = any)",
    "Campaña de reputación (1-4)": "Reputation campaign (1-4)", "Duración de la campaña (h)": "Campaign length (h)",
    "Hora del resumen diario (0-23)": "Daily summary hour (0-23)",
    "Compra inteligente con el histórico de precios": "Smart buying with the price history",
    "Reparar aviones desgastados": "Repair worn aircraft", "Planificar A-checks": "Plan A-checks",
    "Crear rutas para aviones aparcados": "Create routes for parked aircraft",
    "Ampliar el hangar si se llena": "Expand the hangar when it fills up",
    "Asientos business / first según demanda": "Business / first seats by demand",
    "Comprar aviones": "Buy aircraft", "Ahorrar para un avión objetivo": "Save for a goal aircraft",
    "Invertir en pequeños si adelantan el objetivo": "Buy small ones if they bring the goal closer",
    "Despegar aviones": "Depart aircraft", "Comprar fuel": "Buy fuel", "Comprar CO2": "Buy CO2",
    "Campañas de reputación": "Reputation campaigns", "Campaña eco-friendly": "Eco-friendly campaign",
    "Vigilar el checklist del juego": "Watch the game checklist", "Iniciar el bot al abrir": "Start the bot on launch",
    "Mantener sesión del navegador": "Keep the browser session", "Navegador oculto (headless)": "Hidden browser (headless)",
    "Notificaciones por Telegram": "Telegram notifications", "Telegram: también los despegues": "Telegram: departures too",
    "Reiniciar solo tras un error": "Restart by itself after an error", "Simulación (no gasta nada)": "Dry run (spends nothing)",
    "Avión objetivo": "Goal aircraft", "Modelo fijo sin objetivo": "Fixed model without goal",
    # ---- sidebar
    "PERFIL": "PROFILE", "➕ Nuevo perfil…": "➕ New profile…", "CUENTA": "ACCOUNT", "Correo": "E-mail",
    "Contraseña": "Password", "Recordar credenciales": "Remember credentials", "▶  INICIAR BOT": "▶  START BOT",
    "■  PARAR BOT": "■  STOP BOT", "⟳  Ejecutar ciclo ahora": "⟳  Run a cycle now", "ESTADO": "STATUS",
    "APARIENCIA": "APPEARANCE", "IDIOMA": "LANGUAGE", "Claro": "Light", "Oscuro": "Dark", "Sistema": "System",
    "Juego en modo {mode}": "Game in {mode} mode", "fácil": "easy", "realista": "realism",
    "🌐  Abrir el panel web": "🌐  Open the web dashboard",
    "Abre {url} en el navegador: las mismas estadísticas, registro y ajustes.":
        "Opens {url} in the browser: the same statistics, log and settings.",
    "Próxima revisión en {time}": "Next check in {time}", "Revisando ...": "Checking ...",
    "Reinicio automático en {time}": "Automatic restart in {time}",
    "Nuevo perfil": "New profile",
    "Nombre del perfil nuevo (por ejemplo «realismo»).\nTendrá su propia cuenta, ajustes, datos y panel web.":
        "Name of the new profile (for example “realism”).\nIt gets its own account, settings, data and web dashboard.",
    # ---- bot states (bot.BotState values)
    "Parado": "Stopped", "Abriendo navegador": "Opening browser", "Iniciando sesión": "Logging in",
    "En marcha": "Running", "Parando": "Stopping", "Error": "Error",
    # ---- tiles
    "💰  DINERO": "💰  MONEY", "⭐  REPUTACIÓN": "⭐  REPUTATION", "⛽  FUEL": "⛽  FUEL", "🌿  CO2": "🌿  CO2",
    "🛩  FLOTA": "🛩  FLEET", "🎯  OBJETIVO": "🎯  GOAL",
    "+{money}/día": "+{money}/day", "{n} puntos": "{n} points", "campaña {time}": "campaign {time}",
    "sin campaña activa": "no campaign running", "compra ≤ {price}": "buy ≤ {price}", "{n} en vuelo": "{n} flying",
    "{n} aparc.": "{n} parked", "{n} pend.": "{n} pending", "actualizado {time}": "updated {time}",
    "Sin datos todavía": "No data yet",
    # ---- tabs
    "Guardar ajustes": "Save settings", "vacío = más rentable": "empty = most profitable",
    "(mín. visto ${price})": "(lowest seen ${price})",
    "Precio más bajo visto: ${price} el %d/%m/%Y a las %H:%M": "Lowest price seen: ${price} on %d/%m/%Y at %H:%M",
    "Probar Telegram": "Test Telegram",
    "Telegram configurado para el chat {chat} (config/secrets.ini).": "Telegram set up for chat {chat} (config/secrets.ini).",
    "Telegram sin configurar: añade bot_token y chat_id en la sección [telegram] de config/secrets.ini.":
        "Telegram not set up: add bot_token and chat_id to the [telegram] section of config/secrets.ini.",
    # ---- goal panel
    "🎯 Sin objetivo": "🎯 No goal", "🎯 Elige un avión objetivo": "🎯 Pick a goal aircraft",
    "Escribe o elige un modelo en «Avión objetivo» y pulsa Guardar ajustes.":
        "Type or pick a model in “Goal aircraft” and press Save settings.",
    "No encuentro ese modelo en el mercado guardado. Revisa el nombre o espera a que el bot consulte el mercado.":
        "That model is not in the saved market. Check the name or wait until the bot reads the market.",
    "Ahorrado {have} ({pct}%), la reserva aparte.": "Saved {have} ({pct}%), the reserve kept apart.",
    "¡Ya llega! Lo pedirá en la próxima revisión si hay hueco en el hangar.":
        "Enough! It is ordered at the next check if the hangar has room.",
    "Faltan {missing} · {rate} · llegada {eta}": "{missing} to go · {rate} · arrives {eta}",
    "{money}/día": "{money}/day", "ritmo aún sin medir": "rate not measured yet",
    "Hangar: {free} huecos libres de {total}": "Hangar: {free} free slots of {total}",
    "Modo ahorro apagado: compra el avión más rentable que pueda.": "Savings mode off: buys the most profitable aircraft it can.",
    "Compra pequeños solo si se amortizan antes de llegar.": "Buys small ones only if they pay back before the goal.",
    "Solo ahorra: no compra otros aviones.": "Only saves: buys no other aircraft.",
    "IDEAS DE OBJETIVO · precio · plazas · rentabilidad estimada · llegada a tu ritmo":
        "GOAL IDEAS · price · seats · estimated profit · arrival at your pace",
    "Escalera (a tu ritmo actual y al crecer):": "Ladder (at your current pace and as you grow):",
    "Caprichos:": "Dream aircraft:",
    "{name} · {price} · {seats} pax · gana {profit}/día · se paga en {days} d":
        "{name} · {price} · {seats} pax · earns {profit}/day · pays back in {days} d",
    "El bot guardará la lista del mercado la próxima vez que lo consulte.":
        "The bot saves the market list the next time it reads it.",
    "Automático (escalera)": "Automatic (ladder)", "Automático": "Automatic", "Auto: {name}": "Auto: {name}",
    "sin estimar": "not estimated", "ya": "now", "menos de 1 h": "under 1 h", "~{n} días": "~{n} days",
    # ---- log panel
    "📜  Registro": "📜  Log", "Abrir fichero": "Open file", "Limpiar": "Clear",
    # ---- web API answers
    "El bot ya está en marcha.": "The bot is already running.", "Iniciando el bot ...": "Starting the bot ...",
    "El bot ya está parado.": "The bot is already stopped.", "Parando ...": "Stopping ...",
    "Revisando ahora.": "Checking now.", "Cerrando ...": "Closing ...", "Acción desconocida.": "Unknown action.",
    "Guardado.": "Saved.", "«{key}» debe ser un número entero.": "“{key}” must be a whole number.",
    "Ajuste desconocido «{key}».": "Unknown setting “{key}”.",
}
