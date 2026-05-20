"""
Smoke test minimale per il Pellet ERS.

Genera un G-code sintetico con due polilinee separate da un travel,
applica il processore e verifica che:
- il file output contenga piu' righe (split eseguito)
- le righe estrudenti rispettino la conservazione del volume di estrusione
- i feedrate emessi siano multipli di 60 mm/min e >= 60.
"""

import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src import GCodeProcessor, ProcessorConfig, Profile


def _gen_input(path: str) -> None:
    lines = [
        "; sintetico",
        "M83",                       # estrusione relativa
        "G1 X0 Y0 Z0.2 F1500",       # posizionamento
        # polilinea 1: 4 segmenti da 10 mm
        "G1 X10 Y0 E1.0 F1500",
        "G1 X20 Y0 E1.0",
        "G1 X30 Y0 E1.0",
        "G1 X40 Y0 E1.0",
        # travel lungo
        "G1 X100 Y20 F6000",
        # polilinea 2: 3 segmenti da 5 mm
        "G1 X105 Y20 E0.5 F1500",
        "G1 X110 Y20 E0.5",
        "G1 X115 Y20 E0.5",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _check_output(path: str) -> None:
    n_lines = 0
    n_extr = 0
    total_E = 0.0
    bad_F = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            n_lines += 1
            s = raw.strip()
            if not s.startswith("G1"):
                continue
            params = {}
            tokens = s.split(";", 1)[0].split()
            for t in tokens[1:]:
                if not t:
                    continue
                params[t[0]] = float(t[1:])
            if "E" in params and params["E"] > 0 and ("X" in params or "Y" in params):
                n_extr += 1
                total_E += params["E"]
                if "F" in params:
                    F = params["F"]
                    if F < 60.0 or abs(F / 60.0 - round(F / 60.0)) > 1e-6:
                        bad_F.append(F)
    print(f"  righe output:        {n_lines}")
    print(f"  righe estrudenti:    {n_extr}")
    print(f"  E totale (rel):      {total_E:.5f}")
    print(f"  F non quantizzati:   {bad_F[:5]}")
    expected_E = 4 * 1.0 + 3 * 0.5  # 5.5
    assert abs(total_E - expected_E) < 1e-3, f"E totale {total_E} != atteso {expected_E}"
    assert not bad_F, f"feedrate non quantizzati: {bad_F}"
    print("  OK: volume di estrusione conservato e feedrate quantizzati.")


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        in_path = os.path.join(d, "in.gcode")
        out_path = os.path.join(d, "out.gcode")
        _gen_input(in_path)

        cfg = ProcessorConfig(
            max_volumetric_extrusion_rate_slope=1.0,
            pellet_ers_deceleration_slope=0.5,
            max_seg_len=2.0,
            travel_threshold=3.0,
            pellet_ers_min_rate=0.5,
            profile=Profile.LINEAR,
        )
        proc = GCodeProcessor(cfg)
        stats = proc.process_file(in_path, out_path)

        print(f"polilinee: trovate={stats.polylines_found}, "
              f"dopo merge={stats.polylines_after_merge}")
        print(f"righe estrudenti: {stats.extruding_lines}, "
              f"split: {stats.lines_split}, micro-seg: {stats.micro_segments_emitted}")
        print(f"boundary rampup={stats.boundary_rampups}, "
              f"rampdown={stats.boundary_rampdowns}")

        # ci aspettiamo 2 polilinee, entrambi i bordi attivi
        assert stats.polylines_found == 2, stats.polylines_found
        assert stats.polylines_after_merge == 2
        assert stats.boundary_rampups >= 1
        assert stats.boundary_rampdowns >= 1
        assert stats.lines_split >= 1

        _check_output(out_path)


if __name__ == "__main__":
    main()
    print("ALL OK")
