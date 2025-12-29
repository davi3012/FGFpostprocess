"""
Analizzatore di percorsi di estrusione

Identifica percorsi continui di estrusione nel G-code.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .gcode_parser import GCodeCommand


@dataclass
class Point:
    """Punto 3D con estrusione."""
    x: float
    y: float
    z: float
    e: float
    
    def distance_xy(self, other: "Point") -> float:
        """Calcola distanza 2D (XY) da un altro punto."""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx * dx + dy * dy)


@dataclass 
class ExtrusionMove:
    """Singolo movimento di estrusione."""
    command: GCodeCommand
    start_point: Point
    end_point: Point
    length: float  # Lunghezza XY del movimento
    extrusion: float  # Quantità di materiale estruso (E delta)
    feedrate: float
    
    @property
    def line_number(self) -> int:
        return self.command.line_number


@dataclass
class ExtrusionPath:
    """Percorso continuo di estrusione (sequenza di movimenti)."""
    moves: List[ExtrusionMove] = field(default_factory=list)
    feature_type: str = "unknown"
    start_line: int = 0
    end_line: int = 0
    
    @property
    def total_length(self) -> float:
        """Lunghezza totale del percorso in mm."""
        return sum(m.length for m in self.moves)
    
    @property
    def total_extrusion(self) -> float:
        """Estrusione totale del percorso."""
        return sum(m.extrusion for m in self.moves)
    
    @property
    def move_count(self) -> int:
        """Numero di movimenti nel percorso."""
        return len(self.moves)
    
    def is_valid(self, min_length: float = 0.0) -> bool:
        """Verifica se il percorso è valido per il processing."""
        return self.total_length >= min_length and self.move_count > 0


@dataclass
class MachineState:
    """Stato corrente della macchina durante il parsing."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0
    f: float = 1200.0
    relative_extrusion: bool = False
    current_feature: str = "unknown"
    
    def get_position(self) -> Point:
        """Restituisce la posizione corrente come Point."""
        return Point(self.x, self.y, self.z, self.e)
    
    def update_from_command(self, cmd: GCodeCommand) -> None:
        """Aggiorna lo stato in base a un comando G-code."""
        if cmd.command == "G1" or cmd.command == "G0":
            if "X" in cmd.params:
                self.x = cmd.params["X"]
            if "Y" in cmd.params:
                self.y = cmd.params["Y"]
            if "Z" in cmd.params:
                self.z = cmd.params["Z"]
            if "F" in cmd.params:
                self.f = cmd.params["F"]
            if "E" in cmd.params:
                if self.relative_extrusion:
                    self.e += cmd.params["E"]
                else:
                    self.e = cmd.params["E"]
        
        elif cmd.command == "G92":
            # Reset assi
            if "E" in cmd.params:
                self.e = cmd.params["E"]
            if "X" in cmd.params:
                self.x = cmd.params["X"]
            if "Y" in cmd.params:
                self.y = cmd.params["Y"]
            if "Z" in cmd.params:
                self.z = cmd.params["Z"]
        
        elif cmd.command == "M82":
            self.relative_extrusion = False
        
        elif cmd.command == "M83":
            self.relative_extrusion = True


class PathAnalyzer:
    """Analizza il G-code per identificare percorsi di estrusione."""
    
    def __init__(self):
        self.state = MachineState()
    
    def reset(self) -> None:
        """Reset dello stato del parser."""
        self.state = MachineState()
    
    def _is_extrusion_move(self, cmd: GCodeCommand) -> bool:
        """Verifica se un comando è un movimento con estrusione positiva."""
        if cmd.command != "G1":
            return False
        
        has_xy = "X" in cmd.params or "Y" in cmd.params
        has_e = "E" in cmd.params
        
        if not (has_xy and has_e):
            return False
        
        e_value = cmd.params["E"]
        
        if self.state.relative_extrusion:
            return e_value > 0
        else:
            return e_value > self.state.e
    
    def _create_extrusion_move(self, cmd: GCodeCommand) -> ExtrusionMove:
        """Crea un ExtrusionMove da un comando G-code."""
        start_point = self.state.get_position()
        
        # Calcola end point
        end_x = cmd.params.get("X", self.state.x)
        end_y = cmd.params.get("Y", self.state.y)
        end_z = cmd.params.get("Z", self.state.z)
        
        e_param = cmd.params.get("E", self.state.e)
        if self.state.relative_extrusion:
            end_e = self.state.e + e_param
            extrusion = e_param
        else:
            end_e = e_param
            extrusion = e_param - self.state.e
        
        end_point = Point(end_x, end_y, end_z, end_e)
        
        # Calcola lunghezza XY
        length = start_point.distance_xy(end_point)
        
        # Feedrate
        feedrate = cmd.params.get("F", self.state.f)
        
        return ExtrusionMove(
            command=cmd,
            start_point=start_point,
            end_point=end_point,
            length=length,
            extrusion=extrusion,
            feedrate=feedrate
        )
    
    def _detect_feature_type(self, cmd: GCodeCommand) -> Optional[str]:
        """Rileva il tipo di feature dal commento del comando."""
        if cmd.comment:
            comment_upper = cmd.comment.upper()
            if "TYPE:" in comment_upper:
                # Formato: ;TYPE:WALL-OUTER
                return cmd.comment.split(":")[-1].strip()
        return None
    
    def analyze(self, commands: List[GCodeCommand]) -> List[ExtrusionPath]:
        """
        Analizza i comandi e identifica i percorsi di estrusione.
        
        Args:
            commands: Lista di comandi G-code parsati
            
        Returns:
            Lista di ExtrusionPath identificati
        """
        self.reset()
        paths: List[ExtrusionPath] = []
        current_path: Optional[ExtrusionPath] = None
        
        for cmd in commands:
            # Rileva cambio feature type
            feature = self._detect_feature_type(cmd)
            if feature:
                # Chiudi percorso corrente se presente
                if current_path and current_path.moves:
                    current_path.end_line = current_path.moves[-1].line_number
                    paths.append(current_path)
                    current_path = None
                self.state.current_feature = feature
            
            # Chiudi percorso se incontriamo commenti di fine estrusione
            if cmd.comment and any(marker in cmd.comment for marker in ["WIPE_START", "WIPE_END"]):
                if current_path and current_path.moves:
                    current_path.end_line = current_path.moves[-1].line_number
                    paths.append(current_path)
                    current_path = None
                continue
            
            # Gestisci comandi che cambiano modalità
            if cmd.command in ("M82", "M83", "G92"):
                # Chiudi percorso corrente
                if current_path and current_path.moves:
                    current_path.end_line = current_path.moves[-1].line_number
                    paths.append(current_path)
                    current_path = None
                self.state.update_from_command(cmd)
                continue
            
            # Verifica se è movimento di estrusione
            if self._is_extrusion_move(cmd):
                # Crea nuovo percorso se necessario
                if current_path is None:
                    current_path = ExtrusionPath(
                        feature_type=self.state.current_feature,
                        start_line=cmd.line_number
                    )
                
                # Aggiungi movimento al percorso
                move = self._create_extrusion_move(cmd)
                current_path.moves.append(move)
                
                # Aggiorna stato
                self.state.update_from_command(cmd)
            
            elif cmd.command in ("G0", "G1"):
                # Distingui tra travel move e feedrate-only command
                has_movement = any(axis in cmd.params for axis in ["X", "Y", "Z"])
                
                if has_movement:
                    # Movimento senza estrusione (travel) - chiude il percorso
                    if current_path and current_path.moves:
                        current_path.end_line = current_path.moves[-1].line_number
                        paths.append(current_path)
                        current_path = None
                # else: comando solo feedrate (G1 F...) - non chiude percorso
                
                self.state.update_from_command(cmd)
            
            else:
                # Altri comandi (M codes, ecc) - aggiorna stato se necessario
                self.state.update_from_command(cmd)
        
        # Chiudi ultimo percorso
        if current_path and current_path.moves:
            current_path.end_line = current_path.moves[-1].line_number
            paths.append(current_path)
        
        return paths
