"""
FGF G-code Post Processor - CLI (Pellet ERS)

Utilizzo:
    python main.py input.gcode output.gcode [opzioni]

Esempio:
    python main.py in.gcode out.gcode \\
        --slope-pos 1.0 --slope-neg 0.5 \\
        --max-seg-len 2.0 --travel-threshold 3.0 \\
        --min-rate 0.5 --profile linear \\
        --filament-diameter 1.75
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import GCodeProcessor, ProcessorConfig, Profile


def parse_profile(value: str) -> Profile:
    try:
        return Profile(value.lower())
    except ValueError:
        valid = [p.value for p in Profile]
        raise argparse.ArgumentTypeError(
            f"Profilo non valido: '{value}'. Valori validi: {valid}"
        )


def main() -> None:
    p = argparse.ArgumentParser(
        description="FGF G-code Post Processor - Pellet ERS (smoothing volumetrico)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", type=str, help="File G-code di input")
    p.add_argument("output", type=str, help="File G-code di output")

    p.add_argument(
        "--slope-pos", type=float, default=150.0,
        help="Pendenza accelerazione del flusso (mm^3/s^2). Default: 150.0",
    )
    p.add_argument(
        "--slope-neg", type=float, default=0.0,
        help="Pendenza decelerazione (mm^3/s^2). Se <=0 usa --slope-pos. Default: 0.0",
    )
    p.add_argument(
        "--max-seg-len", type=float, default=1.0,
        help="Lunghezza max dei sotto-segmenti dello split (mm). Default: 1.0",
    )
    p.add_argument(
        "--travel-threshold", type=float, default=3.0,
        help="Soglia travel XY per attivare le rampe di confine (mm). Default: 3.0",
    )
    p.add_argument(
        "--min-rate", type=float, default=50.0,
        help="Flusso ai bordi della rampa (mm^3/s). Default: 50.0",
    )
    p.add_argument(
        "--profile", type=parse_profile, default=Profile.SQRT,
        help="Profilo della rampa di feedrate: linear|sqrt|exponential. Default: sqrt",
    )

    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Errore: file non trovato: {args.input}", file=sys.stderr)
        sys.exit(1)

    cfg = ProcessorConfig(
        max_volumetric_extrusion_rate_slope=args.slope_pos,
        pellet_ers_deceleration_slope=args.slope_neg,
        max_seg_len=args.max_seg_len,
        travel_threshold=args.travel_threshold,
        pellet_ers_min_rate=args.min_rate,
        profile=args.profile,
    )

    print("=" * 64)
    print("FGF G-code Post Processor - Pellet ERS")
    print("=" * 64)
    print(f"  slope_pos        : {cfg.max_volumetric_extrusion_rate_slope} mm^3/s^2 "
          f"({cfg.slope_pos_min:.1f} mm^3/min^2)")
    print(f"  slope_neg        : {cfg.pellet_ers_deceleration_slope} mm^3/s^2 "
          f"({cfg.slope_neg_min:.1f} mm^3/min^2)")
    print(f"  max_seg_len      : {cfg.max_seg_len} mm")
    print(f"  travel_threshold : {cfg.travel_threshold} mm")
    print(f"  min_rate         : {cfg.pellet_ers_min_rate} mm^3/s "
          f"({cfg.min_rate_min:.1f} mm^3/min)")
    print(f"  profile          : {cfg.profile.value}")
    print()

    proc = GCodeProcessor(cfg)
    stats = proc.process_file(str(in_path), args.output)

    print("=" * 64)
    print("Statistiche:")
    print(f"  Linee input            : {stats.input_lines}")
    print(f"  Linee output           : {stats.output_lines}")
    print(f"  Polilinee trovate      : {stats.polylines_found}")
    print(f"  Polilinee dopo merge   : {stats.polylines_after_merge}")
    print(f"  Righe estrudenti       : {stats.extruding_lines}")
    print(f"  Righe splittate        : {stats.lines_split}")
    print(f"  Micro-segmenti emessi  : {stats.micro_segments_emitted}")
    print(f"  Boundary ramp-up       : {stats.boundary_rampups}")
    print(f"  Boundary ramp-down     : {stats.boundary_rampdowns}")
    print(f"  Tempo                  : {stats.processing_time:.2f}s")
    print("=" * 64)


if __name__ == "__main__":
    main()
