"""
Parser G-code robusto

Gestisce lettura, parsing e scrittura di comandi G-code.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple


@dataclass
class GCodeCommand:
    """Rappresenta un singolo comando G-code parsato."""
    line_number: int
    raw_line: str
    command: Optional[str] = None  # es. "G1", "M104", None per commenti
    params: Dict[str, float] = field(default_factory=dict)
    comment: Optional[str] = None
    _modified: bool = field(default=False, repr=False)
    
    @property
    def is_movement(self) -> bool:
        """Verifica se è un comando di movimento (G0 o G1)."""
        return self.command in ("G0", "G1")
    
    @property
    def is_extrusion_move(self) -> bool:
        """Verifica se è un movimento con estrusione positiva."""
        if self.command != "G1":
            return False
        has_xy = "X" in self.params or "Y" in self.params
        has_e = "E" in self.params
        return has_xy and has_e
    
    @property
    def is_travel_move(self) -> bool:
        """Verifica se è un movimento senza estrusione (travel)."""
        if self.command not in ("G0", "G1"):
            return False
        has_xy = "X" in self.params or "Y" in self.params
        has_e = "E" in self.params
        return has_xy and not has_e
    
    def to_gcode(self) -> str:
        """Converte il comando in stringa G-code."""
        # Se non modificato, restituisci la linea originale
        if not self._modified:
            return self.raw_line
        
        if self.command is None:
            # Solo commento o linea vuota
            if self.comment:
                return f";{self.comment}"
            return ""
        
        parts = [self.command]
        
        # Ordine standard dei parametri
        param_order = ["X", "Y", "Z", "E", "F"]
        for param in param_order:
            if param in self.params:
                value = self.params[param]
                if param == "E":
                    parts.append(f"{param}{value:.5f}")
                elif param == "F":
                    parts.append(f"{param}{value:.1f}")
                else:
                    parts.append(f"{param}{value:.3f}")
        
        # Altri parametri non standard
        for param, value in self.params.items():
            if param not in param_order:
                parts.append(f"{param}{value}")
        
        result = " ".join(parts)
        
        if self.comment:
            result += f" ;{self.comment}"
        
        return result


class GCodeParser:
    """Parser per file G-code."""
    
    # Pattern per parsing parametri G-code
    # Gestisce: X100, X-100, X100.5, X.5, X-.5
    PARAM_PATTERN = re.compile(r"([A-Z])(-?\.?\d+\.?\d*)")
    
    def parse_line(self, line: str, line_number: int = 0) -> GCodeCommand:
        """
        Parsa una singola linea di G-code.
        
        Args:
            line: Linea raw da parsare
            line_number: Numero di linea nel file
            
        Returns:
            GCodeCommand con i dati parsati
        """
        raw_line = line.rstrip("\n\r")
        line = raw_line.strip()
        
        # Linea vuota
        if not line:
            return GCodeCommand(line_number=line_number, raw_line=raw_line)
        
        # Separa commento
        comment = None
        if ";" in line:
            code_part, comment = line.split(";", 1)
            code_part = code_part.strip()
            comment = comment.strip()
        else:
            code_part = line
        
        # Solo commento
        if not code_part:
            return GCodeCommand(
                line_number=line_number,
                raw_line=raw_line,
                comment=comment
            )
        
        # Estrai comando (es. G1, M104)
        parts = code_part.split()
        if not parts:
            return GCodeCommand(
                line_number=line_number,
                raw_line=raw_line,
                comment=comment
            )
        
        command = parts[0].upper()
        
        # Parsa parametri
        params = {}
        param_str = code_part[len(parts[0]):].strip()
        
        for match in self.PARAM_PATTERN.finditer(param_str):
            param_name = match.group(1)
            param_value = float(match.group(2))
            params[param_name] = param_value
        
        return GCodeCommand(
            line_number=line_number,
            raw_line=raw_line,
            command=command,
            params=params,
            comment=comment
        )
    
    def parse_file(self, filepath: str) -> List[GCodeCommand]:
        """
        Parsa un intero file G-code.
        
        Args:
            filepath: Percorso del file
            
        Returns:
            Lista di GCodeCommand
        """
        commands = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                cmd = self.parse_line(line, line_num)
                commands.append(cmd)
        return commands


def write_gcode(commands: List[GCodeCommand], filepath: str) -> None:
    """
    Scrive una lista di comandi in un file G-code.
    
    Args:
        commands: Lista di GCodeCommand da scrivere
        filepath: Percorso del file di output
    """
    with open(filepath, "w", encoding="utf-8") as f:
        for cmd in commands:
            f.write(cmd.to_gcode() + "\n")
