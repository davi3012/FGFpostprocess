"""
Curve e logica di pressure smoothing

Gestisce le curve matematiche per accelerazione/decelerazione della pressione.
"""

import math
from enum import Enum
from typing import Callable


class CurveType(Enum):
    """Tipi di curve per accelerazione/decelerazione."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    LOGARITHMIC = "logarithmic"
    SIGMOID = "sigmoid"
    QUADRATIC = "quadratic"
    SCURVE = "scurve"


def apply_curve(progress: float, curve_type: CurveType) -> float:
    """
    Applica una curva di smoothing al progresso.
    
    Args:
        progress: Valore tra 0.0 e 1.0 che indica il progresso
        curve_type: Tipo di curva da applicare
        
    Returns:
        Valore trasformato tra 0.0 e 1.0
    """
    # Clamp del progresso tra 0 e 1
    progress = max(0.0, min(1.0, progress))
    
    if curve_type == CurveType.LINEAR:
        return progress
    
    elif curve_type == CurveType.EXPONENTIAL:
        # Accelerazione rapida iniziale, poi rallenta
        return (math.exp(progress * 2) - 1) / (math.exp(2) - 1)
    
    elif curve_type == CurveType.LOGARITHMIC:
        # Accelerazione lenta iniziale, poi accelera
        return math.log(1 + progress * (math.e - 1))
    
    elif curve_type == CurveType.SIGMOID:
        # Curva a S centrata - smooth all'inizio e alla fine
        return 1 / (1 + math.exp(-10 * (progress - 0.5)))
    
    elif curve_type == CurveType.QUADRATIC:
        # Accelerazione quadratica
        return progress * progress
    
    elif curve_type == CurveType.SCURVE:
        # S-Curve ottimizzata per pellet extruder
        # Prima metà: accelerazione quadratica
        # Seconda metà: decelerazione quadratica
        if progress < 0.5:
            return 2 * progress * progress
        else:
            return 1 - 2 * (1 - progress) * (1 - progress)
    
    else:
        return progress


def calculate_speed_factor(
    distance_from_start: float,
    distance_to_end: float,
    ramp_up_length: float,
    ramp_down_length: float,
    ramp_up_curve: CurveType,
    ramp_down_curve: CurveType
) -> float:
    """
    Calcola il fattore di velocità per una posizione nel percorso.
    
    Il fattore va da 0.0 (velocità minima) a 1.0 (velocità piena).
    
    Args:
        distance_from_start: Distanza dall'inizio del percorso (mm)
        distance_to_end: Distanza dalla fine del percorso (mm)
        ramp_up_length: Lunghezza della rampa di accelerazione (mm)
        ramp_down_length: Lunghezza della rampa di decelerazione (mm)
        ramp_up_curve: Tipo di curva per ramp-up
        ramp_down_curve: Tipo di curva per ramp-down
        
    Returns:
        Fattore di velocità tra 0.0 e 1.0
    """
    # Caso: siamo nella zona di ramp-up
    if distance_from_start < ramp_up_length:
        progress = distance_from_start / ramp_up_length
        return apply_curve(progress, ramp_up_curve)
    
    # Caso: siamo nella zona di ramp-down
    if distance_to_end < ramp_down_length:
        progress = distance_to_end / ramp_down_length
        return apply_curve(progress, ramp_down_curve)
    
    # Caso: siamo nella zona steady (velocità piena)
    return 1.0


def calculate_effective_ramps(
    path_length: float,
    ramp_up_length: float,
    ramp_down_length: float,
    max_ramp_ratio: float = 0.8
) -> tuple[float, float]:
    """
    Calcola le lunghezze effettive delle rampe, adattandole alla lunghezza del percorso.
    
    Se il percorso è troppo corto, le rampe vengono ridotte proporzionalmente.
    
    Args:
        path_length: Lunghezza totale del percorso (mm)
        ramp_up_length: Lunghezza desiderata ramp-up (mm)
        ramp_down_length: Lunghezza desiderata ramp-down (mm)
        max_ramp_ratio: Percentuale massima del percorso occupabile dalle rampe
        
    Returns:
        Tuple (effective_ramp_up, effective_ramp_down)
    """
    total_ramp = ramp_up_length + ramp_down_length
    max_total_ramp = path_length * max_ramp_ratio
    
    if total_ramp <= max_total_ramp:
        # Le rampe ci stanno, usale come sono
        return ramp_up_length, ramp_down_length
    
    # Riduci proporzionalmente
    ratio = max_total_ramp / total_ramp
    return ramp_up_length * ratio, ramp_down_length * ratio
