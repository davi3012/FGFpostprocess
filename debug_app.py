"""
FGF G-code Post Processor - Pellet ERS

Web UI minimale: carica un G-code, processa, scarica.

Esegui in locale con:
    streamlit run debug_app.py
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from src import GCodeProcessor, Profile
from src.processor import ProcessorConfig


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FGF Post Processor — Pellet ERS",
    page_icon="🟠",
    layout="centered",
)

st.title("🟠 FGF Post Processor — Pellet ERS")
st.caption(
    "Smoothing volumetrico per stampanti FGF a pellet. "
    "Carica un G-code, premi **Processa**, scarica il risultato."
)

# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

DEFAULTS = {
    "slope_pos": 150.0,           # mm^3/s^2
    "slope_neg": 0.0,             # 0 = usa slope_pos
    "max_seg_len": 1.0,           # mm
    "travel_threshold": 3.0,      # mm
    "min_rate": 50.0,             # mm^3/s
    "profile": Profile.SQRT.value,
}


# ---------------------------------------------------------------------------
# 1) Upload
# ---------------------------------------------------------------------------

st.subheader("1. Carica il G-code")

uploaded = st.file_uploader(
    "File G-code (.gcode / .gco / .nc)",
    type=["gcode", "gco", "nc"],
    label_visibility="collapsed",
)

# ---------------------------------------------------------------------------
# 2) Parametri (con valori sensati di default + expander avanzati)
# ---------------------------------------------------------------------------

st.subheader("2. Parametri")

c1, c2, c3 = st.columns(3)
with c1:
    slope_pos = st.number_input(
        "Slope flusso (mm³/s²)",
        min_value=0.1, max_value=10000.0,
        value=DEFAULTS["slope_pos"], step=10.0,
        help="Quanto in fretta il flusso volumetrico può variare. "
             "Più alto = transizioni più aggressive.",
    )
with c2:
    min_rate = st.number_input(
        "Flusso ai bordi (mm³/s)",
        min_value=0.0, max_value=1000.0,
        value=DEFAULTS["min_rate"], step=5.0,
        help="Valore di flusso volumetrico all'inizio/fine di ogni polilinea.",
    )
with c3:
    max_seg_len = st.number_input(
        "Risoluzione split (mm)",
        min_value=0.1, max_value=10.0,
        value=DEFAULTS["max_seg_len"], step=0.1,
        help="Lunghezza massima di un micro-segmento generato dallo split.",
    )

with st.expander("Parametri avanzati"):
    a1, a2, a3 = st.columns(3)
    with a1:
        slope_neg = st.number_input(
            "Slope decelerazione (mm³/s²)",
            min_value=0.0, max_value=10000.0,
            value=DEFAULTS["slope_neg"], step=10.0,
            help="0 = usa lo stesso valore dello slope di accelerazione.",
        )
    with a2:
        travel_threshold = st.number_input(
            "Soglia travel (mm)",
            min_value=0.0, max_value=50.0,
            value=DEFAULTS["travel_threshold"], step=0.5,
            help="Travel XY minimo per attivare le rampe di inizio/fine polilinea.",
        )
    with a3:
        profile_value = st.selectbox(
            "Profilo rampa",
            [p.value for p in Profile],
            index=[p.value for p in Profile].index(DEFAULTS["profile"]),
            help="Forma della curva di interpolazione del feedrate nelle rampe.",
        )

st.caption(
    "ℹ️ La E del G-code è già in **mm³** (per estrusori a pellet Grasshopper "
    "applica il filament_diameter a monte): non serve specificare alcuna sezione."
)

# ---------------------------------------------------------------------------
# 3) Processa
# ---------------------------------------------------------------------------

st.subheader("3. Processa")

if uploaded is None:
    st.info("👆 Carica un file G-code per iniziare.")
    st.stop()

st.success(f"📄 File caricato: **{uploaded.name}** ({uploaded.size/1024:.1f} KB)")

if "result" not in st.session_state:
    st.session_state.result = None

if st.button("🚀 Processa G-code", type="primary", use_container_width=True):
    cfg = ProcessorConfig(
        max_volumetric_extrusion_rate_slope=slope_pos,
        pellet_ers_deceleration_slope=slope_neg,
        max_seg_len=max_seg_len,
        travel_threshold=travel_threshold,
        pellet_ers_min_rate=min_rate,
        profile=Profile(profile_value),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = os.path.join(tmpdir, uploaded.name)
        out_path = os.path.join(tmpdir, "processed.gcode")
        with open(in_path, "wb") as f:
            f.write(uploaded.getvalue())

        progress = st.progress(0, text="Processing...")
        t0 = time.time()
        processor = GCodeProcessor(cfg)
        stats = processor.process_file(in_path, out_path)
        progress.progress(100, text=f"Fatto in {time.time()-t0:.1f}s")

        with open(out_path, "rb") as f:
            output_bytes = f.read()

    st.session_state.result = {
        "name": Path(uploaded.name).stem + "_processed.gcode",
        "data": output_bytes,
        "stats": stats,
    }

# ---------------------------------------------------------------------------
# 4) Risultato + download
# ---------------------------------------------------------------------------

result = st.session_state.result
if result is not None:
    st.subheader("4. Risultato")
    s = result["stats"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Linee in/out", f"{s.input_lines:,} → {s.output_lines:,}")
    m2.metric("Polilinee", f"{s.polylines_after_merge}",
              help=f"{s.polylines_found} prima del merge")
    m3.metric("Micro-segmenti", f"{s.micro_segments_emitted:,}")
    m4.metric("Tempo", f"{s.processing_time:.1f}s")

    n1, n2, n3 = st.columns(3)
    n1.metric("Righe estrudenti", f"{s.extruding_lines:,}")
    n2.metric("Righe splittate", f"{s.lines_split:,}")
    n3.metric("Rampe up / down",
              f"{s.boundary_rampups} / {s.boundary_rampdowns}")

    st.download_button(
        label="📥 Scarica G-code processato",
        data=result["data"],
        file_name=result["name"],
        mime="text/plain",
        type="primary",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption("FGF G-code Post Processor v2.0.0 · Pellet ERS")
