"""
FGF G-code Post Processor - Debug UI (Pellet ERS)

Interfaccia Streamlit per il post-processing volumetrico Pellet ERS.

Esegui con: streamlit run debug_app.py
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src import GCodeProcessor, Profile
from src.processor import ProcessorConfig
from src.smoothing import interpolate_feedrate


st.set_page_config(
    page_title="FGF Post Processor - Pellet ERS",
    page_icon="🔧",
    layout="wide",
)

st.title("🔧 FGF G-code Post Processor — Pellet ERS")


# ---------------------------------------------------------------------------
# Visualizzazione
# ---------------------------------------------------------------------------


_PARAM_RE = re.compile(r"([XYZEF])(-?\.?\d+\.?\d*)")


def parse_gcode_for_visualization(filepath: str) -> list[dict]:
    """Parsa G-code ed estrae punti per la visualizzazione 3D."""
    points: list[dict] = []
    pos = {"X": 0.0, "Y": 0.0, "Z": 0.0, "E": 0.0, "F": 1500.0}
    relative_e = False

    with open(filepath, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("M83"):
                relative_e = True
                continue
            if line.startswith("M82"):
                relative_e = False
                continue
            if line.startswith("G92"):
                for m in _PARAM_RE.finditer(line):
                    if m.group(1) == "E":
                        pos["E"] = float(m.group(2))
                continue
            if not (line.startswith("G1") or line.startswith("G0")):
                continue

            params = {m.group(1): float(m.group(2)) for m in _PARAM_RE.finditer(line)}

            is_extrusion = False
            if "E" in params:
                if relative_e:
                    is_extrusion = params["E"] > 0
                    pos["E"] += params["E"]
                else:
                    is_extrusion = params["E"] > pos["E"]
                    pos["E"] = params["E"]

            has_xy = False
            if "X" in params:
                pos["X"] = params["X"]
                has_xy = True
            if "Y" in params:
                pos["Y"] = params["Y"]
                has_xy = True
            if "Z" in params:
                pos["Z"] = params["Z"]
            if "F" in params:
                pos["F"] = params["F"]

            if has_xy:
                points.append({
                    "x": pos["X"], "y": pos["Y"], "z": pos["Z"],
                    "f": pos["F"], "extrusion": is_extrusion,
                })
    return points


def create_3d_plot(points: list[dict], extrusion_only: bool = True,
                   z_range: tuple | None = None) -> go.Figure:
    if extrusion_only:
        pts = [p for p in points if p["extrusion"]]
    else:
        pts = points
    if z_range:
        pts = [p for p in pts if z_range[0] <= p["z"] <= z_range[1]]
    if not pts:
        return go.Figure()

    fig = go.Figure(go.Scatter3d(
        x=[p["x"] for p in pts],
        y=[p["y"] for p in pts],
        z=[p["z"] for p in pts],
        mode="lines",
        line=dict(
            color=[p["f"] for p in pts],
            colorscale="Turbo",
            width=2,
            colorbar=dict(title="F (mm/min)", thickness=20),
        ),
        hovertemplate="X:%{x:.2f}<br>Y:%{y:.2f}<br>Z:%{z:.2f}<extra></extra>",
    ))
    fig.update_layout(
        scene=dict(xaxis_title="X (mm)", yaxis_title="Y (mm)", zaxis_title="Z (mm)",
                   aspectmode="data"),
        margin=dict(l=0, r=0, t=20, b=0),
        height=600,
    )
    return fig


def plot_profile_preview() -> go.Figure:
    """Confronto delle 3 forme di rampa (Linear, Sqrt, Exponential)."""
    t = np.linspace(0, 1, 200)
    fig = go.Figure()
    f_start, f_end = 100.0, 1500.0
    for prof in Profile:
        ys = [interpolate_feedrate(f_start, f_end, ti, prof) for ti in t]
        fig.add_trace(go.Scatter(x=t, y=ys, mode="lines", name=prof.value))
    fig.update_layout(
        title="Profili di rampa F (ramp-up 100→1500 mm/min)",
        xaxis_title="t (0-1)", yaxis_title="F (mm/min)",
        height=320, margin=dict(l=0, r=0, t=40, b=0),
    )
    return fig


# ---------------------------------------------------------------------------
# Sidebar - parametri ERS
# ---------------------------------------------------------------------------

st.sidebar.header("⚙️ Parametri Pellet ERS")

slope_pos = st.sidebar.number_input(
    "max_volumetric_extrusion_rate_slope (mm³/s²)",
    min_value=0.01, max_value=1000.0, value=1.0, step=0.1,
)
slope_neg = st.sidebar.number_input(
    "pellet_ers_deceleration_slope (mm³/s², 0 = usa slope_pos)",
    min_value=0.0, max_value=1000.0, value=0.0, step=0.1,
)
filament_diameter = st.sidebar.number_input(
    "pellet_flow_coefficient / filament_diameter (mm)",
    min_value=0.5, max_value=10.0, value=1.75, step=0.05,
)
max_seg_len = st.sidebar.slider(
    "max_seg_len (mm)", 0.5, 10.0, 2.0, 0.5,
)
travel_threshold = st.sidebar.slider(
    "travel_threshold (mm)", 0.0, 20.0, 3.0, 0.5,
)
min_rate = st.sidebar.number_input(
    "pellet_ers_min_rate (mm³/s)",
    min_value=0.0, max_value=100.0, value=0.5, step=0.1,
)
profile_value = st.sidebar.selectbox(
    "pellet_ers_ramp_profile",
    [p.value for p in Profile],
    index=[p.value for p in Profile].index(Profile.SQRT.value),
)

with st.sidebar.expander("📈 Preview profili rampa"):
    st.plotly_chart(plot_profile_preview(), use_container_width=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

st.header("📂 G-code Post Processor")

uploaded_file = st.file_uploader("Carica file G-code", type=["gcode", "gco", "nc"])

if uploaded_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode") as tmp:
        tmp.write(uploaded_file.getvalue())
        input_path = tmp.name

    st.success(f"✅ File caricato: {uploaded_file.name}")

    if st.button("▶️ Processa G-code", type="primary", use_container_width=True):
        cfg = ProcessorConfig(
            max_volumetric_extrusion_rate_slope=slope_pos,
            pellet_ers_deceleration_slope=slope_neg,
            pellet_flow_coefficient=filament_diameter,
            max_seg_len=max_seg_len,
            travel_threshold=travel_threshold,
            pellet_ers_min_rate=min_rate,
            profile=Profile(profile_value),
        )

        output_path = input_path.replace(".gcode", "_processed.gcode")

        with st.spinner("🔄 Processing in corso..."):
            processor = GCodeProcessor(cfg)
            stats = processor.process_file(input_path, output_path)

        st.success("✅ Processing completato!")

        st.subheader("📊 Statistiche")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Linee input", f"{stats.input_lines:,}")
        c2.metric("Linee output", f"{stats.output_lines:,}")
        c3.metric("Polilinee (post-merge)",
                  f"{stats.polylines_after_merge}",
                  delta=f"trovate {stats.polylines_found}")
        c4.metric("Tempo", f"{stats.processing_time:.2f}s")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Righe estrudenti", f"{stats.extruding_lines:,}")
        c6.metric("Righe splittate", f"{stats.lines_split:,}")
        c7.metric("Micro-segmenti", f"{stats.micro_segments_emitted:,}")
        c8.metric("Boundary up/down",
                  f"{stats.boundary_rampups}/{stats.boundary_rampdowns}")

        with open(output_path, "r", encoding="utf-8") as f:
            output_content = f.read()

        st.download_button(
            label="📥 Download G-code processato",
            data=output_content,
            file_name=f"{Path(uploaded_file.name).stem}_processed.gcode",
            mime="text/plain",
            type="primary",
            use_container_width=True,
        )

        # Visualizzazione 3D opzionale
        with st.expander("🧭 Anteprima 3D feedrate (output)"):
            try:
                pts = parse_gcode_for_visualization(output_path)
                if pts:
                    st.plotly_chart(create_3d_plot(pts), use_container_width=True)
                else:
                    st.info("Nessun punto da mostrare.")
            except Exception as e:
                st.warning(f"Impossibile generare la preview: {e}")

        try:
            os.unlink(output_path)
            os.unlink(input_path)
        except OSError:
            pass
else:
    st.info("👆 Carica un file G-code per iniziare")

st.markdown("---")
st.caption("FGF G-code Post Processor v2.0.0 — Pellet ERS Debug UI")
