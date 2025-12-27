"""
Script di validazione per verificare la correttezza del post-processing.

Controlla:
1. Conservazione volume estrusione (E totale)
2. Correttezza delle rampe
3. Feedrate nei range attesi
"""

import re
import sys
from pathlib import Path


def parse_gcode_line(line: str) -> dict:
    """Estrae parametri da una linea G-code."""
    result = {"raw": line.strip()}
    
    # Pattern per parametri
    param_pattern = re.compile(r"([A-Z])(-?\.?\d+\.?\d*)")
    
    # Estrai comando
    parts = line.strip().split()
    if parts and parts[0].startswith("G"):
        result["command"] = parts[0]
    
    # Estrai parametri
    for match in param_pattern.finditer(line):
        param = match.group(1)
        value = float(match.group(2))
        result[param] = value
    
    return result


def analyze_file(filepath: str) -> dict:
    """Analizza un file G-code e restituisce statistiche."""
    stats = {
        "total_lines": 0,
        "g1_lines": 0,
        "extrusion_moves": 0,
        "total_e": 0.0,
        "min_feedrate": float("inf"),
        "max_feedrate": 0.0,
        "feedrates": [],
        "smoothing_blocks": 0,
        "ramp_up_moves": 0,
        "ramp_down_moves": 0,
        "steady_moves": 0,
    }
    
    relative_extrusion = False
    current_e = 0.0
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stats["total_lines"] += 1
            line = line.strip()
            
            # Rileva modalità estrusione
            if line.startswith("M83"):
                relative_extrusion = True
            elif line.startswith("M82"):
                relative_extrusion = False
            elif line.startswith("G92") and "E" in line:
                # Reset E
                parsed = parse_gcode_line(line)
                if "E" in parsed:
                    current_e = parsed["E"]
            
            # Conta blocchi smoothing
            if "PRESSURE_SMOOTHING_START" in line:
                stats["smoothing_blocks"] += 1
            
            # Analizza movimenti G1
            if line.startswith("G1"):
                stats["g1_lines"] += 1
                parsed = parse_gcode_line(line)
                
                # Feedrate
                if "F" in parsed:
                    f_val = parsed["F"]
                    stats["feedrates"].append(f_val)
                    stats["min_feedrate"] = min(stats["min_feedrate"], f_val)
                    stats["max_feedrate"] = max(stats["max_feedrate"], f_val)
                
                # Estrusione
                if "E" in parsed:
                    e_val = parsed["E"]
                    if relative_extrusion:
                        if e_val > 0:
                            stats["total_e"] += e_val
                            stats["extrusion_moves"] += 1
                    else:
                        if e_val > current_e:
                            stats["total_e"] += (e_val - current_e)
                            stats["extrusion_moves"] += 1
                        current_e = e_val
                
                # Conta fasi smoothing
                if "RAMP_UP" in line:
                    stats["ramp_up_moves"] += 1
                elif "RAMP_DOWN" in line:
                    stats["ramp_down_moves"] += 1
                elif "STEADY" in line:
                    stats["steady_moves"] += 1
    
    return stats


def compare_files(input_file: str, output_file: str):
    """Confronta input e output per validare il processing."""
    print("=" * 60)
    print("VALIDAZIONE POST-PROCESSING")
    print("=" * 60)
    
    print(f"\nAnalisi INPUT: {input_file}")
    input_stats = analyze_file(input_file)
    
    print(f"Analisi OUTPUT: {output_file}")
    output_stats = analyze_file(output_file)
    
    # Report
    print("\n" + "-" * 60)
    print("STATISTICHE INPUT:")
    print(f"  Linee totali:      {input_stats['total_lines']}")
    print(f"  Movimenti G1:      {input_stats['g1_lines']}")
    print(f"  Movimenti estrusi: {input_stats['extrusion_moves']}")
    print(f"  Estrusione totale: {input_stats['total_e']:.5f}")
    print(f"  Feedrate min/max:  {input_stats['min_feedrate']:.1f} / {input_stats['max_feedrate']:.1f}")
    
    print("\n" + "-" * 60)
    print("STATISTICHE OUTPUT:")
    print(f"  Linee totali:      {output_stats['total_lines']}")
    print(f"  Movimenti G1:      {output_stats['g1_lines']}")
    print(f"  Movimenti estrusi: {output_stats['extrusion_moves']}")
    print(f"  Estrusione totale: {output_stats['total_e']:.5f}")
    print(f"  Feedrate min/max:  {output_stats['min_feedrate']:.1f} / {output_stats['max_feedrate']:.1f}")
    print(f"  Blocchi smoothing: {output_stats['smoothing_blocks']}")
    print(f"  Movimenti RAMP_UP:   {output_stats['ramp_up_moves']}")
    print(f"  Movimenti STEADY:    {output_stats['steady_moves']}")
    print(f"  Movimenti RAMP_DOWN: {output_stats['ramp_down_moves']}")
    
    # Validazione
    print("\n" + "=" * 60)
    print("VALIDAZIONE:")
    
    # 1. Conservazione volume
    e_diff = abs(output_stats['total_e'] - input_stats['total_e'])
    e_pct = (e_diff / input_stats['total_e'] * 100) if input_stats['total_e'] > 0 else 0
    
    if e_pct < 0.01:
        print(f"  [OK] Volume estrusione conservato (diff: {e_diff:.5f}, {e_pct:.4f}%)")
    else:
        print(f"  [!!] Volume estrusione DIVERSO (diff: {e_diff:.5f}, {e_pct:.2f}%)")
    
    # 2. Feedrate sensati
    if output_stats['min_feedrate'] > 0:
        print(f"  [OK] Feedrate minimo > 0 ({output_stats['min_feedrate']:.1f})")
    else:
        print(f"  [!!] Feedrate minimo = 0 (problema!)")
    
    # 3. Smoothing applicato
    if output_stats['smoothing_blocks'] > 0:
        print(f"  [OK] Smoothing applicato a {output_stats['smoothing_blocks']} percorsi")
    else:
        print(f"  [!!] Nessun blocco smoothing trovato!")
    
    # 4. Distribuzione fasi
    total_smoothed = output_stats['ramp_up_moves'] + output_stats['steady_moves'] + output_stats['ramp_down_moves']
    if total_smoothed > 0:
        up_pct = output_stats['ramp_up_moves'] / total_smoothed * 100
        steady_pct = output_stats['steady_moves'] / total_smoothed * 100
        down_pct = output_stats['ramp_down_moves'] / total_smoothed * 100
        print(f"  [INFO] Distribuzione fasi: RAMP_UP {up_pct:.1f}%, STEADY {steady_pct:.1f}%, RAMP_DOWN {down_pct:.1f}%")
    
    print("=" * 60)


if __name__ == "__main__":
    input_file = "examples/D02_PETG_9h52m.gcode"
    output_file = "examples/output_test.gcode"
    
    if len(sys.argv) >= 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
    
    compare_files(input_file, output_file)
