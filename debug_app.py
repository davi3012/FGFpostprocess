"""
FGF G-code Post Processor - Debug UI

Interfaccia Streamlit per visualizzare e debuggare il post-processing.

Esegui con: streamlit run debug_app.py
"""

import streamlit as st
import plotly.graph_objects as go
import numpy as np
import tempfile
import os
from pathlib import Path

from src import GCodeProcessor, CurveType
from src.processor import ProcessorConfig
from src.gcode_parser import GCodeParser
from src.smoothing import apply_curve


st.set_page_config(
    page_title="FGF Post Processor Debug",
    page_icon="🔧",
    layout="wide"
)

st.title("🔧 FGF G-code Post Processor - Debug")


def parse_gcode_for_visualization(filepath: str) -> dict:
    """Parsa G-code ed estrae dati per visualizzazione."""
    points = []
    current_pos = {"X": 0, "Y": 0, "Z": 0, "E": 0, "F": 1000}
    relative_e = False
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            
            if line.startswith("M83"):
                relative_e = True
            elif line.startswith("M82"):
                relative_e = False
            elif line.startswith("G92"):
                # Reset E
                import re
                for match in re.finditer(r"E(-?\.?\d+\.?\d*)", line):
                    current_pos["E"] = float(match.group(1))
            elif line.startswith("G1") or line.startswith("G0"):
                # Estrai parametri
                params = {}
                import re
                for match in re.finditer(r"([XYZEF])(-?\.?\d+\.?\d*)", line):
                    params[match.group(1)] = float(match.group(2))
                
                # Determina se è estrusione PRIMA di aggiornare posizione
                is_extrusion = False
                if "E" in params:
                    e_val = params["E"]
                    if relative_e:
                        # Estrusione relativa: positivo = estrude, negativo = retract
                        is_extrusion = e_val > 0
                        current_pos["E"] += e_val
                    else:
                        # Estrusione assoluta: confronta con valore precedente
                        is_extrusion = e_val > current_pos["E"]
                        current_pos["E"] = e_val
                
                # Aggiorna posizione
                has_xy_move = False
                if "X" in params:
                    current_pos["X"] = params["X"]
                    has_xy_move = True
                if "Y" in params:
                    current_pos["Y"] = params["Y"]
                    has_xy_move = True
                if "Z" in params:
                    current_pos["Z"] = params["Z"]
                if "F" in params:
                    current_pos["F"] = params["F"]
                
                # Aggiungi punto solo se c'è movimento XY
                if has_xy_move:
                    points.append({
                        "x": current_pos["X"],
                        "y": current_pos["Y"],
                        "z": current_pos["Z"],
                        "f": current_pos["F"],
                        "extrusion": is_extrusion
                    })
    
    return points


def create_3d_plot(points: list, color_by_feedrate: bool = True, 
                   extrusion_only: bool = True, z_range: tuple = None) -> go.Figure:
    """Crea plot 3D del G-code colorato per feedrate."""
    
    # Filtra punti
    if extrusion_only:
        filtered = [p for p in points if p["extrusion"]]
    else:
        filtered = points
    
    if z_range:
        filtered = [p for p in filtered if z_range[0] <= p["z"] <= z_range[1]]
    
    if not filtered:
        return go.Figure()
    
    x = [p["x"] for p in filtered]
    y = [p["y"] for p in filtered]
    z = [p["z"] for p in filtered]
    f = [p["f"] for p in filtered]
    
    # Normalizza feedrate per colori
    f_min, f_max = min(f), max(f)
    if f_max > f_min:
        f_normalized = [(v - f_min) / (f_max - f_min) for v in f]
    else:
        f_normalized = [0.5] * len(f)
    
    fig = go.Figure()
    
    if color_by_feedrate:
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="lines",
            line=dict(
                color=f,
                colorscale="Turbo",
                width=2,
                colorbar=dict(
                    title="Feedrate (mm/min)",
                    thickness=20
                )
            ),
            hovertemplate="X: %{x:.2f}<br>Y: %{y:.2f}<br>Z: %{z:.2f}<br>F: %{marker.color:.0f}<extra></extra>"
        ))
    else:
        fig.add_trace(go.Scatter3d(
            x=x, y=y, z=z,
            mode="lines",
            line=dict(color="blue", width=2)
        ))
    
    fig.update_layout(
        scene=dict(
            xaxis_title="X (mm)",
            yaxis_title="Y (mm)",
            zaxis_title="Z (mm)",
            aspectmode="data"
        ),
        margin=dict(l=0, r=0, t=30, b=0),
        height=600
    )
    
    return fig


def plot_curve_comparison():
    """Mostra confronto delle curve di smoothing."""
    progress = np.linspace(0, 1, 100)
    
    fig = go.Figure()
    
    for curve_type in CurveType:
        values = [apply_curve(p, curve_type) for p in progress]
        fig.add_trace(go.Scatter(
            x=progress, y=values,
            mode="lines",
            name=curve_type.value
        ))
    
    fig.update_layout(
        title="Curve di Smoothing",
        xaxis_title="Progress (0-1)",
        yaxis_title="Speed Factor (0-1)",
        height=400
    )
    
    return fig


# Sidebar - Parametri
st.sidebar.header("⚙️ Parametri")

ramp_up = st.sidebar.slider("Ramp-up (mm)", 0.5, 20.0, 5.0, 0.5)
ramp_down = st.sidebar.slider("Ramp-down (mm)", 0.5, 20.0, 4.0, 0.5)

curve_options = [c.value for c in CurveType]
curve_up = st.sidebar.selectbox("Curva ramp-up", curve_options, index=curve_options.index("sigmoid"))
curve_down = st.sidebar.selectbox("Curva ramp-down", curve_options, index=curve_options.index("exponential"))

min_length = st.sidebar.slider("Min path length (mm)", 0.0, 10.0, 1.0, 0.5)
min_speed = st.sidebar.slider("Min speed (%)", 1, 50, 10, 1)
resolution = st.sidebar.slider("Resolution (mm)", 0.1, 2.0, 0.5, 0.1)

# Mostra curve
with st.sidebar.expander("📈 Preview Curve"):
    st.plotly_chart(plot_curve_comparison(), use_container_width=True)

# Main area
st.header("📂 G-code Post Processor")

uploaded_file = st.file_uploader("Carica file G-code", type=["gcode", "gco", "nc"])

if uploaded_file:
    # Salva file temporaneo
    with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode") as tmp:
        tmp.write(uploaded_file.getvalue())
        input_path = tmp.name
    
    st.success(f"✅ File caricato: {uploaded_file.name}")
    
    if st.button("▶️ Processa G-code", type="primary", use_container_width=True):
        # Crea configurazione
        config = ProcessorConfig(
            ramp_up_length=ramp_up,
            ramp_down_length=ramp_down,
            ramp_up_curve=CurveType(curve_up),
            ramp_down_curve=CurveType(curve_down),
            min_path_length=min_length,
            min_speed_ratio=min_speed / 100,
            segment_resolution=resolution
        )
        
        # File output temporaneo
        output_path = input_path.replace(".gcode", "_processed.gcode")
        
        # Processa
        with st.spinner("🔄 Processing in corso..."):
            processor = GCodeProcessor(config)
            stats = processor.process_file(input_path, output_path)
        
        st.success("✅ Processing completato!")
        
        # Statistiche
        st.subheader("📊 Statistiche")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Percorsi trovati", f"{stats.paths_found:,}")
        with col2:
            st.metric("Percorsi processati", f"{stats.paths_processed:,}")
        with col3:
            st.metric("Percorsi saltati", f"{stats.paths_skipped:,}")
        with col4:
            st.metric("Tempo", f"{stats.processing_time:.1f}s")
        
        st.metric("Lunghezza totale processata", f"{stats.total_path_length:,.2f} mm")
        
        # Download
        with open(output_path, "r") as f:
            output_content = f.read()
        
        st.download_button(
            label="📥 Download G-code processato",
            data=output_content,
            file_name=f"{uploaded_file.name.replace('.gcode', '')}_processed.gcode",
            mime="text/plain",
            type="primary",
            use_container_width=True
        )
        
        # Cleanup
        try:
            os.unlink(output_path)
            os.unlink(input_path)
        except:
            pass
else:
    st.info("👆 Carica un file G-code per iniziare")

# Footer
st.markdown("---")
st.caption("FGF G-code Post Processor v1.0.0 - Debug UI")
