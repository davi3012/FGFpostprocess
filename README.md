# FGF G-code Post Processor

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://your-app-url.streamlit.app)

Post-processor per G-code ottimizzato per stampanti 3D a pellet (FGF - Fused Granulate Fabrication). Applica pressure smoothing con rampe di accelerazione/decelerazione per compensare il lag di pressione tipico dei sistemi ad estrusione di pellet.

## ✨ Funzionalità Principali

- **🎯 Pressure Smoothing**: Rampe di accelerazione/decelerazione graduali all'inizio e fine dei percorsi di estrusione
- **📊 6 Curve di Smoothing**: Linear, Exponential, Logarithmic, Sigmoid, Quadratic, S-Curve
- **⚖️ Conservazione Volume**: Modifica solo il feedrate (F), mantenendo invariato il volume di estrusione (E)
- **🔍 Segmentazione Intelligente**: Suddivisione automatica dei movimenti lunghi per transizioni graduali
- **🗑️ Rimozione Percorsi Corti**: Elimina automaticamente percorsi troppo brevi che l'estrusore non può gestire
- **🌐 Web UI**: Interfaccia Streamlit per processing interattivo
- **✅ Validazione**: Script di validazione per verificare conservazione volume ed efficacia smoothing

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

### Interfaccia Web (Streamlit)

```bash
streamlit run debug_app.py
```

Apri il browser su `http://localhost:8501` e:
1. Carica il file G-code
2. Configura i parametri nella sidebar
3. Clicca "Processa G-code"
4. Scarica il file processato

## 📋 Parametri

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `--ramp-up` | 5.0 mm | Lunghezza della rampa di accelerazione |
| `--ramp-down` | 4.0 mm | Lunghezza della rampa di decelerazione |
| `--curve-up` | sigmoid | Tipo di curva per accelerazione |
| `--curve-down` | exponential | Tipo di curva per decelerazione |
| `--min-length` | 1.0 mm | Lunghezza minima percorso (percorsi più corti vengono rimossi) |
| `--min-speed` | 0.1 | Velocità minima (10% dell'originale) |
| `--resolution` | 0.5 mm | Risoluzione segmentazione nelle rampe |

## Curve Disponibili

- **LINEAR**: Accelerazione costante
- **EXPONENTIAL**: Accelerazione rapida iniziale
- **LOGARITHMIC**: Accelerazione graduale
- **SIGMOID**: Curva a S, smooth
- **QUADRATIC**: Accelerazione quadratica
- **SCURVE**: S-Curve ottimizzata per sistemi a pellet

## 🧪 Validazione Output

```bash
python validate_output.py
```

Verifica:
- Conservazione volume di estrusione (diff < 0.01%)
- Range feedrate min/max
- Numero percorsi processati
- Distribuzione fasi (RAMP_UP, STEADY, RAMP_DOWN)

## 📊 Esempio Output

```
Configurazione:
  Ramp-up:    5.0mm (sigmoid)
  Ramp-down:  4.0mm (exponential)
  Min length: 10.0mm
  Min speed:  10%
  Resolution: 0.5mm

Parsing: input.gcode
  Linee lette: 273876
Analisi percorsi di estrusione...
  Percorsi trovati: 4251
  Percorsi da processare: 3112
  Percorsi saltati (rimossi): 1139

Completato in 12.41s
  Input: 273876 linee
  Output: 517476 linee
```

## 🏗️ Struttura Progetto

```
FGFpostprocess/
├── src/
│   ├── __init__.py
│   ├── gcode_parser.py      # Parser G-code robusto
│   ├── path_analyzer.py     # Identificazione percorsi di estrusione
│   ├── smoothing.py         # Curve e calcoli smoothing
│   └── processor.py         # Orchestratore principale
├── examples/                # File G-code di esempio
├── debug_app.py            # Interfaccia web Streamlit
├── main.py                 # CLI
├── validate_output.py      # Script validazione
├── analyze_ramps.py        # Analisi rampe per debugging
└── requirements.txt
```

## 🔧 Dettagli Tecnici

### Parser G-code
- Supporta numeri decimali con punto iniziale (es. `E.91468`)
- Gestisce estrusione relativa (M83) e assoluta (M82)
- Preserva comandi non standard e parametri custom

### Segmentazione
- Movimenti lunghi nelle zone di rampa vengono suddivisi in segmenti da 0.5mm (configurabile)
- Ogni segmento ha il proprio feedrate calcolato in base alla curva
- Conservazione del volume: estrusione divisa proporzionalmente tra segmenti

### Chiusura Percorsi
- Percorsi chiusi automaticamente a cambio feature type (`;TYPE:` comment)
- Chiusura prima di `WIPE_START`/`WIPE_END`
- Chiusura su travel moves (G0/G1 senza E)

## 🤝 Contributi

Questo progetto è stato sviluppato per ottimizzare la stampa 3D a pellet. Contributi, issue e feature request sono benvenuti!

## 📝 Licenza

MIT License - vedi LICENSE per dettagli

## 👨‍💻 Autore

Davide Malnati - [GitHub](https://github.com/davi3012)
