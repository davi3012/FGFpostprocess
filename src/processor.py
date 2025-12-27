"""
Processore G-code principale

Orchestratore che coordina parsing, analisi e applicazione del pressure smoothing.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
import time

from .gcode_parser import GCodeParser, GCodeCommand, write_gcode
from .path_analyzer import PathAnalyzer, ExtrusionPath, ExtrusionMove, MachineState, Point
from .smoothing import (
    CurveType, 
    calculate_speed_factor, 
    calculate_effective_ramps
)


@dataclass
class ProcessingStats:
    """Statistiche del processing."""
    input_lines: int = 0
    output_lines: int = 0
    paths_found: int = 0
    paths_processed: int = 0
    paths_skipped: int = 0
    total_path_length: float = 0.0
    processing_time: float = 0.0


@dataclass
class ProcessorConfig:
    """Configurazione del processore."""
    # Lunghezze rampe in mm
    ramp_up_length: float = 5.0
    ramp_down_length: float = 4.0
    
    # Tipi di curve
    ramp_up_curve: CurveType = CurveType.SIGMOID
    ramp_down_curve: CurveType = CurveType.EXPONENTIAL
    
    # Lunghezza minima percorso per applicare smoothing (mm)
    min_path_length: float = 1.0
    
    # Velocità minima come percentuale della velocità originale
    min_speed_ratio: float = 0.1
    
    # Risoluzione segmentazione nelle rampe (mm)
    # Movimenti più lunghi di questo valore vengono suddivisi
    segment_resolution: float = 0.5
    
    # Feature types da processare (None = tutti)
    target_features: Optional[List[str]] = None


class GCodeProcessor:
    """
    Processore principale per post-processing G-code.
    
    Applica pressure smoothing ai percorsi di estrusione per migliorare
    la qualità di stampa su stampanti a pellet.
    """
    
    def __init__(self, config: Optional[ProcessorConfig] = None):
        """
        Inizializza il processore.
        
        Args:
            config: Configurazione del processore. Se None, usa defaults.
        """
        self.config = config or ProcessorConfig()
        self.parser = GCodeParser()
        self.analyzer = PathAnalyzer()
        self.stats = ProcessingStats()
    
    def _should_process_path(self, path: ExtrusionPath) -> bool:
        """Determina se un percorso deve essere processato."""
        # Verifica lunghezza minima
        if path.total_length < self.config.min_path_length:
            return False
        
        # Verifica feature type se specificato
        if self.config.target_features:
            if path.feature_type not in self.config.target_features:
                return False
        
        return True
    
    def _is_in_ramp_zone(self, dist_from_start: float, dist_to_end: float, 
                          ramp_up: float, ramp_down: float) -> bool:
        """Verifica se una posizione è in una zona di rampa."""
        return dist_from_start < ramp_up or dist_to_end < ramp_down
    
    def _generate_segment_command(
        self,
        start_x: float, start_y: float, start_z: float, start_e: float,
        end_x: float, end_y: float, end_z: float, end_e: float,
        feedrate: float, phase: str, speed_factor: float,
        has_z: bool
    ) -> GCodeCommand:
        """Genera un comando G1 per un segmento."""
        params = {
            "X": end_x,
            "Y": end_y,
            "E": end_e,
            "F": feedrate
        }
        if has_z:
            params["Z"] = end_z
        
        return GCodeCommand(
            line_number=0,
            raw_line="",
            command="G1",
            params=params,
            comment=f"{phase} {speed_factor*100:.0f}%",
            _modified=True
        )
    
    def _apply_smoothing_to_path(
        self, 
        path: ExtrusionPath
    ) -> List[GCodeCommand]:
        """
        Applica pressure smoothing a un percorso di estrusione.
        
        Modifica il feedrate (F) per creare accelerazione/decelerazione
        graduale, mantenendo invariato il volume di estrusione (E).
        Segmenta i movimenti lunghi nelle zone di rampa per transizioni graduali.
        
        Args:
            path: Percorso da processare
            
        Returns:
            Lista di comandi G-code modificati
        """
        result: List[GCodeCommand] = []
        
        # Calcola rampe effettive
        eff_ramp_up, eff_ramp_down = calculate_effective_ramps(
            path.total_length,
            self.config.ramp_up_length,
            self.config.ramp_down_length
        )
        
        total_length = path.total_length
        resolution = self.config.segment_resolution
        
        # Aggiungi commento di inizio
        result.append(GCodeCommand(
            line_number=0,
            raw_line="",
            comment=f"PRESSURE_SMOOTHING_START: {path.feature_type}, length={total_length:.2f}mm",
            _modified=True
        ))
        result.append(GCodeCommand(
            line_number=0,
            raw_line="",
            comment=f"Ramps: up={eff_ramp_up:.2f}mm ({self.config.ramp_up_curve.value}), down={eff_ramp_down:.2f}mm ({self.config.ramp_down_curve.value})",
            _modified=True
        ))
        
        # Calcola distanza cumulativa per ogni movimento
        cumulative_distance = 0.0
        
        for move in path.moves:
            move_start_dist = cumulative_distance
            move_end_dist = cumulative_distance + move.length
            
            # Coordinate del movimento
            sx, sy, sz = move.start_point.x, move.start_point.y, move.start_point.z
            ex, ey, ez = move.end_point.x, move.end_point.y, move.end_point.z
            se, ee = move.start_point.e, move.end_point.e
            has_z = "Z" in move.command.params
            
            # Verifica se il movimento attraversa zone di rampa
            in_ramp_up = move_start_dist < eff_ramp_up
            in_ramp_down = move_end_dist > (total_length - eff_ramp_down)
            needs_segmentation = (in_ramp_up or in_ramp_down) and move.length > resolution
            
            if needs_segmentation:
                # Segmenta il movimento
                num_segments = max(2, int(move.length / resolution))
                
                # Estrusione per segmento (usa il delta relativo, non i valori assoluti)
                e_per_segment = move.extrusion / num_segments
                
                for seg_idx in range(num_segments):
                    # Progresso nel movimento (0 to 1)
                    t0 = seg_idx / num_segments
                    t1 = (seg_idx + 1) / num_segments
                    t_mid = (t0 + t1) / 2
                    
                    # Distanza dal percorso per questo segmento
                    seg_dist = move_start_dist + move.length * t_mid
                    seg_dist_to_end = total_length - seg_dist
                    
                    # Calcola speed factor per questo segmento
                    speed_factor = calculate_speed_factor(
                        seg_dist,
                        seg_dist_to_end,
                        eff_ramp_up,
                        eff_ramp_down,
                        self.config.ramp_up_curve,
                        self.config.ramp_down_curve
                    )
                    speed_factor = max(speed_factor, self.config.min_speed_ratio)
                    
                    # Interpola coordinate XYZ
                    seg_ex = sx + (ex - sx) * t1
                    seg_ey = sy + (ey - sy) * t1
                    seg_ez = sz + (ez - sz) * t1
                    
                    # Determina fase
                    if seg_dist < eff_ramp_up:
                        phase = "RAMP_UP"
                    elif seg_dist_to_end < eff_ramp_down:
                        phase = "RAMP_DOWN"
                    else:
                        phase = "STEADY"
                    
                    # Calcola feedrate
                    new_feedrate = move.feedrate * speed_factor
                    
                    cmd = self._generate_segment_command(
                        sx + (ex - sx) * t0, sy + (ey - sy) * t0, sz + (ez - sz) * t0, 0,
                        seg_ex, seg_ey, seg_ez, e_per_segment,
                        new_feedrate, phase, speed_factor, has_z
                    )
                    result.append(cmd)
            else:
                # Movimento non necessita segmentazione
                dist_mid = move_start_dist + move.length / 2
                dist_to_end = total_length - dist_mid
                
                speed_factor = calculate_speed_factor(
                    dist_mid,
                    dist_to_end,
                    eff_ramp_up,
                    eff_ramp_down,
                    self.config.ramp_up_curve,
                    self.config.ramp_down_curve
                )
                speed_factor = max(speed_factor, self.config.min_speed_ratio)
                
                new_feedrate = move.feedrate * speed_factor
                
                # Determina fase
                if dist_mid < eff_ramp_up:
                    phase = f"RAMP_UP {speed_factor*100:.0f}%"
                elif dist_to_end < eff_ramp_down:
                    phase = f"RAMP_DOWN {speed_factor*100:.0f}%"
                else:
                    phase = "STEADY"
                
                new_params = move.command.params.copy()
                new_params["F"] = new_feedrate
                
                original_comment = move.command.comment or ""
                new_comment = f"{original_comment} ; {phase}" if original_comment else phase
                
                new_cmd = GCodeCommand(
                    line_number=move.command.line_number,
                    raw_line=move.command.raw_line,
                    command="G1",
                    params=new_params,
                    comment=new_comment,
                    _modified=True
                )
                result.append(new_cmd)
            
            cumulative_distance = move_end_dist
        
        # Aggiungi commento di fine
        result.append(GCodeCommand(
            line_number=0,
            raw_line="",
            comment="PRESSURE_SMOOTHING_END",
            _modified=True
        ))
        
        return result
    
    def process_file(self, input_path: str, output_path: str) -> ProcessingStats:
        """
        Processa un file G-code applicando pressure smoothing.
        
        Args:
            input_path: Percorso del file G-code di input
            output_path: Percorso del file G-code di output
            
        Returns:
            Statistiche del processing
        """
        start_time = time.time()
        
        # Reset stats
        self.stats = ProcessingStats()
        
        # 1. Parsa il file
        print(f"Parsing: {input_path}")
        commands = self.parser.parse_file(input_path)
        self.stats.input_lines = len(commands)
        print(f"  Linee lette: {self.stats.input_lines}")
        
        # 2. Analizza e identifica percorsi
        print("Analisi percorsi di estrusione...")
        paths = self.analyzer.analyze(commands)
        self.stats.paths_found = len(paths)
        print(f"  Percorsi trovati: {self.stats.paths_found}")
        
        # 3. Crea mappa linea -> percorso per sostituzione efficiente
        line_to_path: Dict[int, ExtrusionPath] = {}
        for path in paths:
            if self._should_process_path(path):
                for move in path.moves:
                    line_to_path[move.line_number] = path
                self.stats.paths_processed += 1
                self.stats.total_path_length += path.total_length
            else:
                self.stats.paths_skipped += 1
        
        print(f"  Percorsi da processare: {self.stats.paths_processed}")
        print(f"  Percorsi saltati: {self.stats.paths_skipped}")
        
        # 4. Genera output
        print("Generazione output...")
        output_commands: List[GCodeCommand] = []
        processed_paths: set = set()
        
        for cmd in commands:
            line_num = cmd.line_number
            
            # Verifica se questa linea fa parte di un percorso da processare
            if line_num in line_to_path:
                path = line_to_path[line_num]
                path_id = path.start_line  # Usa start_line come ID unico
                
                # Processa il percorso solo la prima volta che lo incontriamo
                if path_id not in processed_paths:
                    processed_paths.add(path_id)
                    smoothed_commands = self._apply_smoothing_to_path(path)
                    output_commands.extend(smoothed_commands)
                # Altrimenti salta (già processato)
            else:
                # Linea non parte di un percorso - copia direttamente
                output_commands.append(cmd)
        
        self.stats.output_lines = len(output_commands)
        
        # 5. Scrivi output
        print(f"Scrittura: {output_path}")
        write_gcode(output_commands, output_path)
        
        # Calcola tempo totale
        self.stats.processing_time = time.time() - start_time
        
        print(f"\nCompletato in {self.stats.processing_time:.2f}s")
        print(f"  Input: {self.stats.input_lines} linee")
        print(f"  Output: {self.stats.output_lines} linee")
        
        return self.stats
