# FGF G-code Post Processor

Post-processor per G-code ottimizzato per stampanti 3D a pellet (FGF - Fused Granulate Fabrication).

## Funzionalità

- **Pressure Smoothing**: Accelerazione/decelerazione graduale della velocità all'inizio e fine dei percorsi di estrusione
- **6 Curve di Smoothing**: Linear, Exponential, Logarithmic, Sigmoid, Quadratic, S-Curve
- **Conservazione Volume**: Modifica solo il feedrate (F), mantenendo invariato il volume di estrusione (E)
- **Gestione Percorsi Corti**: Adattamento automatico delle rampe per percorsi brevi

## Installazione

```bash
pip install -r requirements.txt
```

## Utilizzo

### Linea di Comando

```bash
python main.py input.gcode output.gcode
```

Con opzioni:

```bash
python main.py input.gcode output.gcode --ramp-up 6.0 --ramp-down 4.0 --curve-up sigmoid --curve-down exponential
```

### Come Libreria Python

```python
from src import GCodeProcessor, CurveType
from src.processor import ProcessorConfig

config = ProcessorConfig(
    ramp_up_length=5.0,
    ramp_down_length=4.0,
    ramp_up_curve=CurveType.SIGMOID,
    ramp_down_curve=CurveType.EXPONENTIAL,
    min_path_length=1.0
)

processor = GCodeProcessor(config)
stats = processor.process_file("input.gcode", "output.gcode")

print(f"Percorsi processati: {stats.paths_processed}")
```

## Parametri

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `ramp_up_length` | 5.0 mm | Lunghezza della rampa di accelerazione |
| `ramp_down_length` | 4.0 mm | Lunghezza della rampa di decelerazione |
| `ramp_up_curve` | SIGMOID | Tipo di curva per accelerazione |
| `ramp_down_curve` | EXPONENTIAL | Tipo di curva per decelerazione |
| `min_path_length` | 1.0 mm | Lunghezza minima percorso per smoothing |
| `min_speed_ratio` | 0.1 | Velocità minima (10% dell'originale) |

## Curve Disponibili

- **LINEAR**: Accelerazione costante
- **EXPONENTIAL**: Accelerazione rapida iniziale
- **LOGARITHMIC**: Accelerazione graduale
- **SIGMOID**: Curva a S, smooth
- **QUADRATIC**: Accelerazione quadratica
- **SCURVE**: S-Curve ottimizzata per sistemi a pellet

## Struttura Progetto

```
FGFpostprocess/
├── src/
│   ├── __init__.py
│   ├── gcode_parser.py      # Parser G-code
│   ├── path_analyzer.py     # Identificazione percorsi
│   ├── smoothing.py         # Curve e calcoli smoothing
│   └── processor.py         # Orchestratore principale
├── tests/
│   └── __init__.py
├── main.py                  # Entry point CLI
├── requirements.txt
└── README.md
```

## Licenza

Proprietario - Ginger Additive
