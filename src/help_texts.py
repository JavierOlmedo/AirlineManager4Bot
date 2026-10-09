"""Help texts for the hover tooltips (one per control), in Spanish (HELP) and English (HELP_EN).
The README "Guía de la app" says the same. Use ``i18n.tip(key)`` to get the one of the current language."""

HELP = {
    # ---- sidebar
    "language": "Idioma de la ventana y del panel web. También cambia el idioma de tu cuenta en el juego en la "
                "siguiente revisión (el bot funciona con el juego en cualquier idioma). El registro y Telegram siguen "
                "en español.",
    "profile": "Cada perfil es una aerolínea (una cuenta del juego) con sus propios ajustes, credenciales, sesión de "
               "Chrome, datos y panel web. Elige otro para abrirlo en otra ventana (pueden ir a la vez) o crea uno "
               "nuevo: copia tus ajustes actuales y pone un acceso directo en el escritorio.",
    "game_mode": "Modo de la cuenta en el juego, leído en cada revisión. En realista los vuelos van a la velocidad del "
                 "avión y los billetes son más baratos que en fácil (x1,5); el bot ajusta sus cálculos de beneficio, "
                 "rutas y asientos a cada modo.",
    "account": "Tu correo y contraseña de Airline Manager. Si marcas «Recordar credenciales» se guardan en "
               "config/secrets.ini, que no se sube a git. Si los dejas vacíos, inicia sesión a mano en Chrome.",
    "remember": "Guarda el correo y la contraseña en config/secrets.ini para no escribirlos cada vez. "
                "Al desmarcarlo se borra ese fichero.",
    "btn_start": "Abre Chrome, inicia sesión y empieza a revisar la aerolínea en bucle. Guarda los ajustes antes de arrancar.",
    "btn_stop": "Para el bot cuando termine el paso que esté haciendo y cierra Chrome.",
    "btn_run_now": "Se salta la espera y hace una revisión completa ahora mismo.",
    "status": "Estado del bot y cuenta atrás hasta la próxima revisión. Tras un error verás el motivo y la cuenta atrás del "
              "reinicio automático.",
    "theme": "Tema claro, oscuro o el del sistema.",
    # ---- statistic tiles
    "money": "Dinero de la aerolínea. Debajo, los ingresos netos estimados por día mientras el bot está en marcha (el "
             "fuel y el CO2 cuentan al gastarse, no al comprarlos) y los puntos del juego (el bot no los gasta).",
    "fuel": "Lo lleno que está el tanque de fuel. Debajo, el precio actual por 1.000 lbs y el precio por debajo del cual "
            "compra ahora mismo.",
    "co2": "Lo lleno que está el tanque de CO2. Debajo, el precio actual de 1.000 cuotas y el umbral de compra actual.",
    "fleet": "Aviones de la flota. Debajo: en vuelo, aparcados sin ruta y pendientes (de entrega o en el taller cambiando "
             "asientos).",
    "reputation": "Reputación de la aerolínea, con las campañas que estén en marcha. Los aviones vuelan más o menos así de "
                  "llenos. Entre paréntesis, lo que le queda a la primera campaña que acaba.",
    "goal": "Progreso hacia el avión objetivo: dinero ahorrado por encima de la reserva y llegada estimada a tu ritmo de ingresos.",
    # ---- market
    "fuel_price_good": "Por debajo de este precio compra fuel siempre, diga lo que diga el histórico. "
                       "Entre paréntesis, el precio más bajo que ha visto el bot.",
    "co2_price_good": "Por debajo de este precio compra CO2 siempre, diga lo que diga el histórico. "
                      "Entre paréntesis, el precio más bajo que ha visto el bot.",
    "buy_percentile": "Con la compra inteligente, compra cuando el precio está entre el X % más barato de los últimos días. "
                      "25 = el cuarto más barato. Más bajo compra menos veces pero más barato.",
    "excellent_percentile": "Precio excepcional: si el precio está entre el X % más barato, llena el tanque con todo el dinero "
                            "que haya por encima de la reserva y puede volver a comprar en la misma media hora. 0 lo desactiva.",
    "history_days": "Cuántos días de precios usa para calcular los percentiles.",
    "min_stock_pct": "Si el tanque baja de este porcentaje, repone hasta ese nivel a cualquier precio para que ningún avión se quede en tierra.",
    "stock_days": "Como mucho compra fuel o CO2 para estos días de consumo (lo mide el bot); con precio excepcional, el "
                  "doble. Así el dinero va a aviones nuevos en vez de quedarse semanas en el tanque. 0 = llena el tanque.",
    "market_max_spend_pct": "Parte máxima del dinero disponible (por encima de la reserva) que gasta en una compra normal de fuel o CO2.",
    "fuel_quantity_buy": "Cantidad máxima de fuel por compra. Con 9.999.999 llena lo que quepa.",
    "co2_quantity_buy": "Cantidad máxima de CO2 por compra. Con 9.999.999 llena lo que quepa.",
    "cycle_min_minutes": "Espera mínima entre revisiones. El bot elige un tiempo al azar entre el mínimo y el máximo.",
    "cycle_max_minutes": "Espera máxima entre revisiones. Se adelanta solo si va a aterrizar un avión o a cambiar el precio.",
    "smart_buy": "Usa el histórico de precios para decidir: compra cuando el precio está en la parte baja de los últimos días, "
                 "no solo por debajo del precio fijo.",
    # ---- fleet
    "auto_repair": "Planifica la reparación de los aviones cuyo desgaste supere el umbral.",
    "auto_check": "Planifica el A-check cuando a un avión le queden pocas horas.",
    "auto_route": "Da ruta a los aviones aparcados: elige la ruta con más demanda que el avión puede volar y pone el precio automático del juego.",
    "auto_hangar": "Si quedan pocos huecos en el hangar, compra uno más (unos $25.000) para que siempre se pueda comprar otro avión.",
    "repair_wear_pct": "Desgaste a partir del cual se repara un avión.",
    "check_hours_min": "Se planifica el A-check cuando quedan estas horas o menos.",
    "cash_reserve": "Colchón para lo imprescindible: por debajo de esta cantidad solo paga reparaciones, A-checks, el fuel "
                    "o CO2 de un tanque casi vacío y la ruta de un avión ya comprado. Nada de aviones, campañas, taller, "
                    "hangar ni compras normales de fuel.",
    "route_max_distance": "Distancia máxima al buscar ruta para aviones pequeños y medianos.",
    "route_max_distance_big": "Distancia máxima al buscar ruta para aviones de 150 plazas o más. Las rutas largas pagan billetes más caros.",
    "route_min_runway": "Pista mínima del aeropuerto de destino al buscar rutas.",
    "hangar_min_free": "Huecos libres que intenta mantener en el hangar si «Ampliar el hangar» está activado.",
    "fleet_actions_per_cycle": "Máximo de rutas nuevas y pedidos de aviones en cada revisión, para no gastar todo de golpe.",
    "auto_seats": "Cuando un avión está en la base, mira la demanda de su ruta y le pone asientos first y business hasta "
                  "cubrir esa demanda; el resto, turista. Por hueco, first paga más que business y business más que turista. "
                  "Solo cambia si sale a cuenta (ver «amortizar en»).",
    "seats_max_payback": "Solo cambia los asientos o instala una mejora si su coste, más lo que el avión deja de ganar en el "
                         "taller, se recupera en estos días o menos.",
    "auto_mods": "Cuando un avión está en la base, calcula cuánto ganaría con cada mejora del taller del juego: "
                 "velocidad +10 % (más vuelos al día), fuel -10 % y CO2 -10 %. Instala solo las que se pagan en el plazo "
                 "de «amortizar en». Son permanentes y cada una tiene el avión unos 13 minutos en el taller.",
    # ---- aircraft and goal
    "autobuy_aircraft": "Permite al bot comprar aviones. Nunca compra mientras haya aviones aparcados sin ruta.",
    "save_for_goal": "Modo ahorro: junta dinero para el avión objetivo y lo compra en cuanto llega, sin tocar la reserva.",
    "goal_model": "El avión que quieres conseguir. «Automático (escalera)» elige solo el siguiente escalón: el avión que "
                  "más gana al día entre los que cuestan como mucho un día de ingresos y se pagan en 5 días o menos. "
                  "Al crecer los ingresos, la escalera sube sola a aviones más grandes. También puedes elegir un modelo fijo.",
    "goal_invest": "Mientras ahorra, compra un avión más pequeño solo si se amortiza en menos de la mitad del tiempo que falta "
                   "para el objetivo: así el objetivo llega antes. Apagado, solo ahorra.",
    "aircraft_model": "Sin objetivo: compra siempre este modelo en lugar del más rentable.",
    "aircraft_max_price": "Sin objetivo: no compra aviones más caros que esto. 0 = sin límite.",
    # ---- options
    "auto_depart": "Despega todos los aviones que estén listos en cada revisión.",
    "autobuy_fuel": "Compra fuel según las reglas de la pestaña Mercado.",
    "autobuy_co2": "Compra CO2 según las reglas de la pestaña Mercado.",
    "auto_marketing": "Mantiene en marcha una campaña de reputación: los aviones vuelan tan llenos como la reputación, "
                      "así que cada despegue gana más. Solo la lanza si lo que trae en billetes (según tus ingresos "
                      "medidos) supera su precio, y nunca baja de la reserva de caja.",
    "marketing_eco": "Mantiene en marcha la campaña eco-friendly (12 h, +10 % de reputación, barata) mientras salga a "
                     "cuenta. Solo funciona si tienes cuotas de CO2 en el tanque.",
    "auto_checklist": "Lee el checklist del juego (abajo a la izquierda), avisa de las tareas que se completan y cobra "
                      "las recompensas si el juego ofrece un botón.",
    "marketing_campaign": "Qué campaña de reputación lanza: 1 (+5-10 %, la más barata) a 4 (+25-35 %). La 4 es la que "
                          "más reputación da por cada dólar.",
    "marketing_hours": "Duración de cada campaña de reputación: 4, 8, 12, 16, 20 o 24 h. Las largas salen algo más "
                       "baratas por hora, pero siguen corriendo aunque pares el bot.",
    "start_on_launch": "Arranca el bot nada más abrir la aplicación. Útil con el acceso directo en el inicio de Windows.",
    "keep_session": "Guarda el perfil de Chrome en config/session. El juego pide login igualmente, pero conserva cookies y ajustes.",
    "headless": "Chrome sin ventana. Más discreto; si el juego pide un captcha no podrás verlo.",
    "telegram": "Envía a Telegram cada compra, ruta, pedido, reparación, error y un resumen diario.",
    "telegram_departures": "Además, un mensaje en cada despegue. Suele ser demasiado ruido.",
    "auto_restart": "Si el bot se para por un error, vuelve a arrancar solo a los 2 minutos (luego 4, 8... hasta 30).",
    "dry_run": "Simulación: el bot hace todo igual pero no compra ni planifica nada; solo escribe en el registro lo que haría.",
    "summary_hour": "Hora a partir de la cual se envía el resumen diario por Telegram.",
    "telegram_test": "Manda un mensaje de prueba para comprobar el token y el chat id de config/secrets.ini.",
    # ---- panels
    "save": "Guarda los números de esta pestaña. Los interruptores se guardan solos al cambiarlos.",
    "open_log": "Abre data/logs/am4bot.log con todo el detalle, incluido lo que no sale aquí.",
    "clear_log": "Vacía el panel. El fichero de registro no se toca.",
}

HELP_EN = {
    # ---- sidebar
    "language": "Language of the window and the web dashboard. It also switches your game account to that language at "
                "the next check (the bot works with the game in any language). The log and Telegram stay in Spanish.",
    "profile": "Each profile is one airline (one game account) with its own settings, credentials, Chrome session, data "
               "and web dashboard. Pick another one to open it in another window (they can run at the same time) or "
               "create a new one: it copies your current settings and puts a shortcut on the desktop.",
    "game_mode": "Mode of the game account, read at every check. In realism flights go at the aircraft's speed and "
                 "tickets are cheaper than in easy mode (x1.5); the bot adapts its profit, route and seat calculations.",
    "account": "Your Airline Manager e-mail and password. With “Remember credentials” they are saved in "
               "config/secrets.ini, which is never uploaded to git. Leave them empty to log in by hand in Chrome.",
    "remember": "Saves the e-mail and password in config/secrets.ini so you do not type them every time. "
                "Unticking it deletes that file.",
    "btn_start": "Opens Chrome, logs in and keeps checking the airline in a loop. Saves the settings before starting.",
    "btn_stop": "Stops the bot when the current step ends and closes Chrome.",
    "btn_run_now": "Skips the wait and runs a full check right now.",
    "status": "State of the bot and countdown to the next check. After an error you see the reason and the countdown "
              "of the automatic restart.",
    "theme": "Light, dark or the system theme.",
    # ---- statistic tiles
    "money": "Money of the airline. Below, the estimated net income per day while the bot runs (fuel and CO2 count "
             "when burnt, not when bought) and the game points (the bot does not spend them).",
    "fuel": "How full the fuel tank is. Below, the current price per 1,000 lbs and the price under which it buys now.",
    "co2": "How full the CO2 tank is. Below, the current price of 1,000 quotas and the current buy threshold.",
    "fleet": "Aircraft in the fleet. Below: flying, parked without a route and pending (delivery or in the workshop "
             "changing seats).",
    "reputation": "Airline reputation, including running campaigns. Aircraft fly about this full. Below, the time left "
                  "on the first campaign to end.",
    "goal": "Progress towards the goal aircraft: money saved above the reserve and estimated arrival at your income rate.",
    # ---- market
    "fuel_price_good": "Below this price it always buys fuel, whatever the history says. "
                       "In brackets, the lowest price the bot has seen.",
    "co2_price_good": "Below this price it always buys CO2, whatever the history says. "
                      "In brackets, the lowest price the bot has seen.",
    "buy_percentile": "With smart buying, it buys when the price is within the cheapest X % of the last days. "
                      "25 = the cheapest quarter. Lower buys less often but cheaper.",
    "excellent_percentile": "Exceptional price: within the cheapest X % it fills the tank with all the money above the "
                            "reserve and may buy again in the same half hour. 0 turns it off.",
    "history_days": "How many days of prices are used for the percentiles.",
    "min_stock_pct": "If the tank drops below this percentage it tops up to that level at any price, so no aircraft "
                     "stays on the ground.",
    "stock_days": "It buys at most this many days of fuel or CO2 use (measured by the bot); twice that at an exceptional "
                  "price. That way money goes to new aircraft instead of sitting in the tank for weeks. 0 = fills the tank.",
    "market_max_spend_pct": "Largest share of the available money (above the reserve) spent on a normal fuel or CO2 purchase.",
    "fuel_quantity_buy": "Maximum fuel per purchase. With 9,999,999 it fills whatever fits.",
    "co2_quantity_buy": "Maximum CO2 per purchase. With 9,999,999 it fills whatever fits.",
    "cycle_min_minutes": "Minimum wait between checks. The bot picks a random time between the minimum and the maximum.",
    "cycle_max_minutes": "Maximum wait between checks. It comes back earlier when an aircraft is about to land or the "
                         "price is about to change.",
    "smart_buy": "Uses the price history to decide: buys when the price is in the low part of the last days, not only "
                 "below the fixed price.",
    # ---- fleet
    "auto_repair": "Plans the repair of aircraft whose wear passes the threshold.",
    "auto_check": "Plans the A-check when an aircraft has few hours left.",
    "auto_route": "Gives parked aircraft a route: the busiest route the aircraft can fly, with the game's autoprice.",
    "auto_hangar": "When few hangar slots are left it buys one more (about $25,000) so another aircraft can always be bought.",
    "repair_wear_pct": "Wear from which an aircraft is repaired.",
    "check_hours_min": "The A-check is planned when this many hours or fewer are left.",
    "cash_reserve": "Cushion for the essentials: below this amount it only pays repairs, A-checks, fuel or CO2 for a "
                    "nearly empty tank and the route of an aircraft already bought. No aircraft, campaigns, workshop, "
                    "hangar or normal fuel purchases.",
    "route_max_distance": "Maximum distance when searching routes for small and medium aircraft.",
    "route_max_distance_big": "Maximum distance when searching routes for aircraft of 150 seats or more. Long routes "
                              "pay more expensive tickets.",
    "route_min_runway": "Minimum runway of the destination airport when searching routes.",
    "hangar_min_free": "Free hangar slots it tries to keep when “Expand the hangar” is on.",
    "fleet_actions_per_cycle": "Maximum new routes and aircraft orders per check, so it does not spend everything at once.",
    "auto_seats": "When an aircraft is at the base, it reads the demand of its route and gives it first and business "
                  "seats up to that demand; the rest economy. Per slot, first pays more than business and business more "
                  "than economy. It only changes when it pays (see “pay back in”).",
    "seats_max_payback": "It only changes the seats or installs an upgrade if its cost, plus what the aircraft does not earn "
                         "in the workshop, comes back in this many days or fewer.",
    "auto_mods": "When an aircraft is at the base, it works out what each upgrade of the game workshop would earn: "
                 "speed +10 % (more flights a day), fuel -10 % and CO2 -10 %. It only installs those that pay back within "
                 "“pay back in”. They are permanent and each keeps the aircraft about 13 minutes in the workshop.",
    # ---- aircraft and goal
    "autobuy_aircraft": "Lets the bot buy aircraft. It never buys while aircraft are parked without a route.",
    "save_for_goal": "Savings mode: puts money aside for the goal aircraft and buys it as soon as it can, without "
                     "touching the reserve.",
    "goal_model": "The aircraft you want. “Automatic (ladder)” picks the next step by itself: the aircraft that earns "
                  "most per day among those costing at most one day of income and paying back in 5 days or fewer. As "
                  "income grows, the ladder climbs to bigger aircraft. You can also pick a fixed model.",
    "goal_invest": "While saving, it buys a smaller aircraft only if it pays back in less than half the time left to "
                   "the goal: that way the goal comes sooner. Off, it only saves.",
    "aircraft_model": "Without a goal: always buys this model instead of the most profitable one.",
    "aircraft_max_price": "Without a goal: never buys aircraft more expensive than this. 0 = no limit.",
    # ---- options
    "auto_depart": "Departs every aircraft that is ready at each check.",
    "autobuy_fuel": "Buys fuel with the rules of the Market tab.",
    "autobuy_co2": "Buys CO2 with the rules of the Market tab.",
    "auto_marketing": "Keeps a reputation campaign running: aircraft fly as full as the reputation, so every departure "
                      "earns more. It only launches it when the extra tickets (from your measured income) beat its "
                      "price, and never goes below the cash reserve.",
    "marketing_eco": "Keeps the eco-friendly campaign running (12 h, +10 % reputation, cheap) as long as it pays. It "
                     "only works while you hold CO2 quotas.",
    "auto_checklist": "Reads the game checklist (bottom left), reports finished tasks and collects rewards when the game "
                      "offers a button.",
    "marketing_campaign": "Which reputation campaign it launches: 1 (+5-10 %, the cheapest) to 4 (+25-35 %). Number 4 "
                          "gives the most reputation per dollar.",
    "marketing_hours": "Length of each reputation campaign: 4, 8, 12, 16, 20 or 24 h. Long ones are a bit cheaper per "
                       "hour but keep running if you stop the bot.",
    "start_on_launch": "Starts the bot as soon as the app opens. Handy with the shortcut in the Windows startup folder.",
    "keep_session": "Keeps the Chrome profile in the profile folder. The game asks for the login anyway, but cookies and "
                    "settings stay.",
    "headless": "Chrome without a window. More discreet; if the game shows a captcha you will not see it.",
    "telegram": "Sends every purchase, route, order, repair, error and a daily summary to Telegram.",
    "telegram_departures": "Also a message at every departure. Usually too much noise.",
    "auto_restart": "If the bot stops because of an error, it starts again by itself after 2 minutes (then 4, 8... up to 30).",
    "dry_run": "Dry run: the bot does everything the same but buys and plans nothing; it only writes what it would do.",
    "summary_hour": "Hour from which the daily Telegram summary is sent.",
    "telegram_test": "Sends a test message to check the token and chat id of config/secrets.ini.",
    # ---- panels
    "save": "Saves the numbers of this tab. Switches are saved as soon as you change them.",
    "open_log": "Opens data/logs/am4bot.log with all the detail, including what is not shown here.",
    "clear_log": "Empties the panel. The log file is not touched.",
}
