"""
FGF G-code Post Processor - Pellet ERS

Post-processing per stampanti 3D a pellet (FGF - Fused Granulate Fabrication).
Implementa lo smoothing volumetrico Pellet ERS senza marker di slicer.
"""

from .processor import GCodeProcessor, ProcessorConfig, ProcessingStats
from .smoothing import Profile, CurveType, interpolate_feedrate, quantize_feedrate

__version__ = "2.0.0"
__all__ = [
    "GCodeProcessor",
    "ProcessorConfig",
    "ProcessingStats",
    "Profile",
    "CurveType",
    "interpolate_feedrate",
    "quantize_feedrate",
]
