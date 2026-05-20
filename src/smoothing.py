"""
Pellet ERS - profilo di interpolazione del feedrate e utility.

Implementa la specifica matematica del Pellet ERS (sezioni 7.4 e 7.5):
- Profili: Linear, Sqrt, Exponential
- Quantizzazione finale del feedrate

Tutti i valori di feedrate sono in mm/min.
"""

from __future__ import annotations

import math
from enum import Enum


class Profile(str, Enum):
    """Forme della curva di feedrate nelle rampe (spec §7.4)."""
    LINEAR = "linear"
    SQRT = "sqrt"
    EXPONENTIAL = "exponential"


# Compatibilita' retroattiva: alcuni moduli/CLI possono ancora importare CurveType.
CurveType = Profile


def interpolate_feedrate(
    f_start: float,
    f_end: float,
    t: float,
    profile: Profile,
) -> float:
    """
    Interpolazione del feedrate (spec §7.4).

    Args:
        f_start: feedrate all'inizio della rampa (mm/min)
        f_end:   feedrate alla fine della rampa  (mm/min)
        t:       parametro normalizzato in [0, 1]
        profile: forma di curva

    Funziona simmetricamente per ramp-up (f_start < f_end)
    e ramp-down (f_start > f_end).
    """
    if t <= 0.0:
        return f_start
    if t >= 1.0:
        return f_end

    if profile == Profile.LINEAR:
        return f_start + (f_end - f_start) * t

    if profile == Profile.SQRT:
        # F(t) = sqrt(F_start^2 + (F_end^2 - F_start^2) * t)
        v2 = f_start * f_start + (f_end * f_end - f_start * f_start) * t
        if v2 < 0.0:
            v2 = 0.0
        return math.sqrt(v2)

    if profile == Profile.EXPONENTIAL:
        # F(t) = F_end - (F_end - F_start) * exp(-3 * t)
        return f_end - (f_end - f_start) * math.exp(-3.0 * t)

    # fallback
    return f_start + (f_end - f_start) * t


def quantize_feedrate(f: float) -> float:
    """
    Quantizzazione finale del feedrate (spec §7.5):
        F = max(60, F)
        F = round(F / 60) * 60
    """
    if f < 60.0:
        f = 60.0
    return round(f / 60.0) * 60.0
