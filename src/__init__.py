"""
FGF G-code Post Processor

Post-processing per stampanti 3D a pellet (FGF - Fused Granulate Fabrication)
"""

from .processor import GCodeProcessor
from .smoothing import CurveType

__version__ = "1.0.0"
__all__ = ["GCodeProcessor", "CurveType"]
