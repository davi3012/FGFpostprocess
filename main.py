"""
FGF G-code Post Processor - Entry Point CLI

Utilizzo:
    python main.py input.gcode output.gcode [opzioni]
"""

import argparse
import sys
from pathlib import Path

from src import GCodeProcessor, CurveType
from src.processor import ProcessorConfig


def parse_curve_type(value: str) -> CurveType:
    """Converte stringa in CurveType."""
    try:
        return CurveType(value.lower())
    except ValueError:
        valid = [c.value for c in CurveType]
        raise argparse.ArgumentTypeError(
            f"Curva non valida: '{value}'. Valori validi: {valid}"
        )


def main():
    parser = argparse.ArgumentParser(
        description="FGF G-code Post Processor - Pressure Smoothing per stampanti a pellet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python main.py input.gcode output.gcode
  python main.py input.gcode output.gcode --ramp-up 6.0 --ramp-down 4.0
  python main.py input.gcode output.gcode --curve-up sigmoid --curve-down exponential

Curve disponibili:
  linear      - Accelerazione lineare
  exponential - Accelerazione esponenziale
  logarithmic - Accelerazione logaritmica  
  sigmoid     - Curva a S (smooth)
  quadratic   - Accelerazione quadratica
  scurve      - S-Curve ottimizzata per pellet
        """
    )
    
    parser.add_argument(
        "input",
        type=str,
        help="File G-code di input"
    )
    
    parser.add_argument(
        "output", 
        type=str,
        help="File G-code di output"
    )
    
    parser.add_argument(
        "--ramp-up",
        type=float,
        default=5.0,
        help="Lunghezza rampa di accelerazione in mm (default: 5.0)"
    )
    
    parser.add_argument(
        "--ramp-down",
        type=float,
        default=4.0,
        help="Lunghezza rampa di decelerazione in mm (default: 4.0)"
    )
    
    parser.add_argument(
        "--curve-up",
        type=parse_curve_type,
        default=CurveType.SIGMOID,
        help="Tipo di curva per ramp-up (default: sigmoid)"
    )
    
    parser.add_argument(
        "--curve-down",
        type=parse_curve_type,
        default=CurveType.EXPONENTIAL,
        help="Tipo di curva per ramp-down (default: exponential)"
    )
    
    parser.add_argument(
        "--min-length",
        type=float,
        default=1.0,
        help="Lunghezza minima percorso per applicare smoothing in mm (default: 1.0)"
    )
    
    parser.add_argument(
        "--min-speed",
        type=float,
        default=0.1,
        help="Velocità minima come percentuale (0.0-1.0) della velocità originale (default: 0.1)"
    )
    
    parser.add_argument(
        "--resolution",
        type=float,
        default=0.5,
        help="Risoluzione segmentazione nelle rampe in mm (default: 0.5)"
    )
    
    args = parser.parse_args()
    
    # Verifica file input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Errore: File non trovato: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Crea configurazione
    config = ProcessorConfig(
        ramp_up_length=args.ramp_up,
        ramp_down_length=args.ramp_down,
        ramp_up_curve=args.curve_up,
        ramp_down_curve=args.curve_down,
        min_path_length=args.min_length,
        min_speed_ratio=args.min_speed,
        segment_resolution=args.resolution
    )
    
    # Processa
    print("=" * 60)
    print("FGF G-code Post Processor v1.0.0")
    print("=" * 60)
    print(f"\nConfigurazione:")
    print(f"  Ramp-up:    {config.ramp_up_length}mm ({config.ramp_up_curve.value})")
    print(f"  Ramp-down:  {config.ramp_down_length}mm ({config.ramp_down_curve.value})")
    print(f"  Min length: {config.min_path_length}mm")
    print(f"  Min speed:  {config.min_speed_ratio*100:.0f}%")
    print(f"  Resolution: {config.segment_resolution}mm")
    print()
    
    processor = GCodeProcessor(config)
    stats = processor.process_file(str(input_path), args.output)
    
    print("\n" + "=" * 60)
    print("Statistiche:")
    print(f"  Percorsi trovati:    {stats.paths_found}")
    print(f"  Percorsi processati: {stats.paths_processed}")
    print(f"  Percorsi saltati:    {stats.paths_skipped}")
    print(f"  Lunghezza totale:    {stats.total_path_length:.2f}mm")
    print("=" * 60)


if __name__ == "__main__":
    main()
