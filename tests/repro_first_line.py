"""
Riproduce il caso utente: il primo segmento di estrusione di una polilinea
appare emesso INVARIATO (senza ramp-up), mentre le righe successive vengono
splittate.
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import GCodeProcessor, ProcessorConfig, Profile

INPUT = """M83
G91
G1 Z1
G90
G1 F10000 X448.181497 Y595.472695 Z198.25 E0
G91
G1 Z-1
G90
G1 F5000 E15
G1 F2700 X448.096064 Y602.306909 Z198.25 E20.504245
G1 X448.181497 Y617.124750 Z198.250 E43.937700 F2700.0
"""

def main():
    with tempfile.TemporaryDirectory() as d:
        ip = os.path.join(d, "in.gcode")
        op = os.path.join(d, "out.gcode")
        with open(ip, "w") as f:
            f.write(INPUT)
        cfg = ProcessorConfig(
            max_volumetric_extrusion_rate_slope=1.0,
            pellet_ers_deceleration_slope=0.0,
            max_seg_len=2.0,
            travel_threshold=3.0,
            pellet_ers_min_rate=0.5,
            profile=Profile.SQRT,
        )
        proc = GCodeProcessor(cfg)
        stats = proc.process_file(ip, op)
        print(f"polilinee trovate={stats.polylines_found}, dopo merge={stats.polylines_after_merge}")
        print(f"righe estrudenti={stats.extruding_lines}, splittate={stats.lines_split}, microseg={stats.micro_segments_emitted}")
        print(f"boundary rampup={stats.boundary_rampups}, rampdown={stats.boundary_rampdowns}")
        print("---- OUTPUT ----")
        with open(op) as f:
            for i, line in enumerate(f):
                print(f"{i:3d}: {line.rstrip()}")

if __name__ == "__main__":
    main()
