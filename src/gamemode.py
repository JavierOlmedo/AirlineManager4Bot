"""Game mode (easy / realism) and the formulas that change with it.

The game page sets ``var difficulty`` to 1.5 in easy mode and 1 in realism mode, and it is the speed
multiplier of the flights. Verified on 2026-10-05 on one account of each mode: in realism an A320 flew
4,825 km in 5 h 52 min at its listed 823 km/h; in easy mode legs take distance / (1.5 x speed). Ticket
autoprices, verified on both accounts:

    easy:    Y = 0.4 x km + 170, J = 0.8 x km + 560, F = 1.2 x km + 1,200
    realism: Y = 0.3 x km + 150, J = 0.6 x km + 500, F = 0.9 x km + 1,000

Aircraft prices, speeds and fuel use in the market are the same in both modes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GameMode:
    key: str
    label: str
    speed: float                                   # flights fly at listed speed x this
    fares: tuple[tuple[float, float], ...]         # (per km, base) autoprice of Y, J, F

    def fare(self, seat_class: int, km: float) -> float:
        per_km, base = self.fares[seat_class]
        return per_km * km + base

    def distance(self, y_price: float, j_price: Optional[float] = None) -> float:
        """Route length from its autoprices. VIP aircraft sell every class at a multiple of the autoprice;
        J - 2 x Y removes the distance and gives that multiple."""
        (y_km, y_base), (j_km, j_base) = self.fares[0], self.fares[1]
        factor = 1.0
        if j_price and y_price and j_km == 2 * y_km:
            measured = (j_price - 2 * y_price) / (j_base - 2 * y_base)
            # rounding of the prices moves it a few % around 1 on normal aircraft: only trust clear multiples
            if 0.5 <= measured <= 4 and abs(measured - 1) > 0.15:
                factor = measured
        return max(0.0, (y_price / factor - y_base) / y_km)


EASY = GameMode("easy", "fácil", 1.5, ((0.4, 170), (0.8, 560), (1.2, 1200)))
REALISM = GameMode("realism", "realista", 1.0, ((0.3, 150), (0.6, 500), (0.9, 1000)))


def from_difficulty(value) -> Optional[GameMode]:
    """The mode from the page's ``difficulty`` variable; None when it could not be read."""
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return None
    return REALISM if speed < 1.25 else EASY
