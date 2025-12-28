"""
Script per analizzare le rampe nel G-code processato
"""

import re
import sys

def analyze_ramps(filepath: str):
    """Analizza le rampe in un file G-code processato."""
    
    in_smoothing = False
    current_path = None
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            
            if "PRESSURE_SMOOTHING_START" in line:
                # Estrai lunghezza percorso
                match = re.search(r"length=(\d+\.\d+)mm", line)
                if match:
                    path_length = float(match.group(1))
                    current_path = {
                        "length": path_length,
                        "ramp_up_length": 0,
                        "ramp_down_length": 0,
                        "steady_length": 0,
                        "ramp_up_dist": 0,
                        "ramp_down_dist": 0,
                        "moves": []
                    }
                    in_smoothing = True
                    print(f"\n{'='*60}")
                    print(f"PERCORSO: {path_length:.2f}mm")
            
            elif "Ramps:" in line and current_path:
                # Estrai lunghezze rampe configurate
                match_up = re.search(r"up=(\d+\.\d+)mm", line)
                match_down = re.search(r"down=(\d+\.\d+)mm", line)
                if match_up and match_down:
                    current_path["config_ramp_up"] = float(match_up.group(1))
                    current_path["config_ramp_down"] = float(match_down.group(1))
                    print(f"Config: ramp-up={current_path['config_ramp_up']:.2f}mm, ramp-down={current_path['config_ramp_down']:.2f}mm")
            
            elif "PRESSURE_SMOOTHING_END" in line and current_path:
                # Analizza il percorso
                print(f"\nMovimenti totali: {len(current_path['moves'])}")
                
                # Calcola distanze effettive
                cumulative = 0
                ramp_up_end = 0
                ramp_down_start = current_path["length"]
                
                for move in current_path["moves"]:
                    if move["phase"] == "RAMP_UP":
                        ramp_up_end = cumulative + move["length"]
                    if move["phase"] == "RAMP_DOWN" and ramp_down_start == current_path["length"]:
                        ramp_down_start = cumulative
                    cumulative += move["length"]
                
                actual_ramp_up = ramp_up_end
                actual_ramp_down = current_path["length"] - ramp_down_start
                
                print(f"\nRAMP-UP:")
                print(f"  Configurato: {current_path.get('config_ramp_up', 0):.2f}mm")
                print(f"  Effettivo:   {actual_ramp_up:.2f}mm")
                print(f"  Differenza:  {abs(actual_ramp_up - current_path.get('config_ramp_up', 0)):.2f}mm")
                
                print(f"\nRAMP-DOWN:")
                print(f"  Configurato: {current_path.get('config_ramp_down', 0):.2f}mm")
                print(f"  Effettivo:   {actual_ramp_down:.2f}mm")
                print(f"  Differenza:  {abs(actual_ramp_down - current_path.get('config_ramp_down', 0)):.2f}mm")
                
                # Mostra distribuzione speed factor
                ramp_up_moves = [m for m in current_path["moves"] if m["phase"] == "RAMP_UP"]
                ramp_down_moves = [m for m in current_path["moves"] if m["phase"] == "RAMP_DOWN"]
                
                if ramp_up_moves:
                    speeds = [m["speed"] for m in ramp_up_moves]
                    print(f"\nRAMP-UP speed factors: min={min(speeds):.0f}%, max={max(speeds):.0f}%")
                
                if ramp_down_moves:
                    speeds = [m["speed"] for m in ramp_down_moves]
                    print(f"RAMP-DOWN speed factors: min={min(speeds):.0f}%, max={max(speeds):.0f}%")
                
                in_smoothing = False
                current_path = None
                
                # Analizza solo i primi 3 percorsi
                if len([1 for _ in range(3)]) >= 3:
                    break
            
            elif in_smoothing and current_path and line.startswith("G1"):
                # Estrai info movimento
                params = {}
                for match in re.finditer(r"([XYZEF])(-?\.?\d+\.?\d*)", line):
                    params[match.group(1)] = float(match.group(2))
                
                # Estrai fase e speed factor dal commento
                phase = "STEADY"
                speed = 100
                if "RAMP_UP" in line:
                    phase = "RAMP_UP"
                    match = re.search(r"RAMP_UP (\d+)%", line)
                    if match:
                        speed = int(match.group(1))
                elif "RAMP_DOWN" in line:
                    phase = "RAMP_DOWN"
                    match = re.search(r"RAMP_DOWN (\d+)%", line)
                    if match:
                        speed = int(match.group(1))
                
                # Calcola lunghezza movimento (approssimata)
                if len(current_path["moves"]) > 0:
                    prev = current_path["moves"][-1]
                    dx = params.get("X", prev["x"]) - prev["x"]
                    dy = params.get("Y", prev["y"]) - prev["y"]
                    length = (dx**2 + dy**2)**0.5
                else:
                    length = 0
                
                current_path["moves"].append({
                    "x": params.get("X", 0),
                    "y": params.get("Y", 0),
                    "phase": phase,
                    "speed": speed,
                    "length": length
                })


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_ramps.py <gcode_file>")
        sys.exit(1)
    
    analyze_ramps(sys.argv[1])
