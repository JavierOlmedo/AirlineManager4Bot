"""What the user can change, shared by the desktop window and the web dashboard (labels in Spanish).

Numbers live in [settings], switches in [options] of config/settings.ini. Both interfaces build their
tabs from these lists, so a new setting only has to be added here (and to help_texts.HELP).
"""
from __future__ import annotations

# (settings key, label) for the whole-number fields of each tab
MARKET_FIELDS = [
    ("fuel_price_good", "Comprar fuel a ≤ $"),
    ("co2_price_good", "Comprar CO2 a ≤ $"),
    ("min_stock_pct", "Stock mínimo (%)"),
    ("stock_days", "Stock máx. (días)"),
    ("market_max_spend_pct", "Gasto máx. (% caja)"),
    ("cycle_min_minutes", "Espera mín. (min)"),
    ("cycle_max_minutes", "Espera máx. (min)"),
    ("buy_percentile", "Percentil compra (%)"),
    ("excellent_percentile", "Percentil excepc. (%)"),
    ("history_days", "Histórico (días)"),
    ("fuel_quantity_buy", "Máx. fuel / compra"),
    ("co2_quantity_buy", "Máx. CO2 / compra"),
]
FLEET_FIELDS = [
    ("repair_wear_pct", "Reparar a partir de desgaste (%)"),
    ("check_hours_min", "A-check si quedan <= horas"),
    ("cash_reserve", "Reserva de caja ($)"),
    ("route_max_distance", "Ruta máx. avión pequeño (km)"),
    ("route_max_distance_big", "Ruta máx. avión grande (km)"),
    ("route_min_runway", "Pista mínima (ft)"),
    ("hangar_min_free", "Huecos libres en el hangar"),
    ("fleet_actions_per_cycle", "Rutas / pedidos por ciclo"),
    ("seats_max_payback", "Taller: amortizar en ≤ días"),
]
AIRCRAFT_FIELDS = [
    ("aircraft_max_price", "Precio máx. sin objetivo (0 = libre)"),
]
MARKETING_FIELDS = [
    ("marketing_campaign", "Campaña de reputación (1-4)"),
    ("marketing_hours", "Duración de la campaña (h)"),
]
OPTIONS_FIELDS = MARKETING_FIELDS + [
    ("summary_hour", "Hora del resumen diario (0-23)"),
]
ALL_FIELDS = MARKET_FIELDS + FLEET_FIELDS + AIRCRAFT_FIELDS + OPTIONS_FIELDS

# (options key, label) for the switches of each tab
MARKET_SWITCHES = [
    ("smart_buy", "Compra inteligente con el histórico de precios"),
]
FLEET_SWITCHES = [
    ("auto_repair", "Reparar aviones desgastados"),
    ("auto_check", "Planificar A-checks"),
    ("auto_route", "Crear rutas para aviones aparcados"),
    ("auto_hangar", "Ampliar el hangar si se llena"),
    ("auto_seats", "Asientos business / first según demanda"),
    ("auto_mods", "Mejoras de avión: velocidad, fuel y CO2"),
]
AIRCRAFT_SWITCHES = [
    ("autobuy_aircraft", "Comprar aviones"),
    ("save_for_goal", "Ahorrar para un avión objetivo"),
    ("goal_invest", "Invertir en pequeños si adelantan el objetivo"),
]
OPTION_SWITCHES = [
    ("auto_depart", "Despegar aviones"),
    ("autobuy_fuel", "Comprar fuel"),
    ("autobuy_co2", "Comprar CO2"),
    ("auto_marketing", "Campañas de reputación"),
    ("marketing_eco", "Campaña eco-friendly"),
    ("auto_checklist", "Vigilar el checklist del juego"),
    ("start_on_launch", "Iniciar el bot al abrir"),
    ("keep_session", "Mantener sesión del navegador"),
    ("headless", "Navegador oculto (headless)"),
    ("telegram", "Notificaciones por Telegram"),
    ("telegram_departures", "Telegram: también los despegues"),
    ("auto_restart", "Reiniciar solo tras un error"),
    ("dry_run", "Simulación (no gasta nada)"),
]
ALL_SWITCHES = MARKET_SWITCHES + FLEET_SWITCHES + AIRCRAFT_SWITCHES + OPTION_SWITCHES

# Free-text settings (Aviones tab)
TEXT_SETTINGS = [
    ("goal_model", "Avión objetivo"),
    ("aircraft_model", "Modelo fijo sin objetivo"),
]

# Tabs in display order: (name, icon, fields, switches)
TABS = [
    ("Mercado", "🛒", MARKET_FIELDS, MARKET_SWITCHES),
    ("Flota", "🛩️", FLEET_FIELDS, FLEET_SWITCHES),
    ("Aviones", "✈️", AIRCRAFT_FIELDS, AIRCRAFT_SWITCHES),
    ("Opciones", "⚙️", OPTIONS_FIELDS, OPTION_SWITCHES),
]

# Switches that default to on when the key is missing from settings.ini
OPTION_DEFAULTS = {"auto_restart": True, "auto_hangar": True, "goal_invest": True, "auto_seats": True, "auto_mods": True,
                   "auto_marketing": True, "marketing_eco": True, "auto_checklist": True}

_LIMITS = {
    "summary_hour": (0, 23),
    "marketing_campaign": (1, 4),
    "marketing_hours": (4, 24),
    "cycle_min_minutes": (1, None),
}


def parse_int(raw) -> int | None:
    """'200,000' / '200.000' / 200000 -> 200000; None when it is not a whole number."""
    text = str(raw).strip().replace(",", "").replace(".", "")
    return int(text) if text.isdigit() else None


def clamp_settings(values: dict[str, int]) -> dict[str, int]:
    """Keep the numbers inside the ranges the bot understands (in place, also returned)."""
    for key, (low, high) in _LIMITS.items():
        if key in values:
            values[key] = max(low, values[key]) if high is None else max(low, min(high, values[key]))
    if "cycle_max_minutes" in values and "cycle_min_minutes" in values:
        values["cycle_max_minutes"] = max(values["cycle_max_minutes"], values["cycle_min_minutes"])
    return values
