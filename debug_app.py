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
    current_pos = {"X": 0, "Y": 0, "Z": 0, "F": 1000}
    relative_e = False
    
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            
            if line.startswith("M83"):
                relative_e = True
            elif line.startswith("M82"):
                relative_e = False
            elif line.startswith("G1"):
                # Estrai parametri
                params = {}
                import re
                for match in re.finditer(r"([XYZEF])(-?\.?\d+\.?\d*)", line):
                    params[match.group(1)] = float(match.group(2))
                
                # Aggiorna posizione
                has_move = False
                if "X" in params:
                    current_pos["X"] = params["X"]
                    has_move = True
                if "Y" in params:
                    current_pos["Y"] = params["Y"]
                    has_move = True
                if "Z" in params:
                    current_pos["Z"] = params["Z"]
                    has_move = True
                if "F" in params:
                    current_pos["F"] = params["F"]
                
                # Determina se è estrusione
                is_extrusion = "E" in params
                if relative_e and is_extrusion:
                    is_extrusion = params["E"] > 0
                
                if has_move:
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
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📂 Input G-code")
    uploaded_file = st.file_uploader("Carica file G-code", type=["gcode", "gco", "nc"])
    
    if uploaded_file:
        # Salva file temporaneo
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gcode") as tmp:
            tmp.write(uploaded_file.getvalue())
            input_path = tmp.name
        
        st.success(f"File caricato: {uploaded_file.name}")
        
        # Parsing per visualizzazione
        with st.spinner("Parsing G-code..."):
            input_points = parse_gcode_for_visualization(input_path)
        
        st.info(f"Punti trovati: {len(input_points)}")
        
        # Filtro Z
        if input_points:
            z_values = [p["z"] for p in input_points]
            z_min_data, z_max_data = min(z_values), max(z_values)
            
            z_range = st.slider(
                "Filtro Z (layer)",
                float(z_min_data), float(z_max_data),
                (float(z_min_data), min(float(z_min_data) + 5, float(z_max_data))),
                0.1
            )
            
            extrusion_only = st.checkbox("Solo estrusione", value=True)
            
            with st.spinner("Generazione preview 3D..."):
                fig_input = create_3d_plot(input_points, True, extrusion_only, z_range)
            
            st.plotly_chart(fig_input, use_container_width=True)

with col2:
    st.header("🔄 Output Processato")
    
    if uploaded_file and st.button("▶️ Processa G-code", type="primary"):
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
        with st.spinner("Processing..."):
            processor = GCodeProcessor(config)
            stats = processor.process_file(input_path, output_path)
        
        st.success("Processing completato!")
        
        # Statistiche
        col_stats1, col_stats2 = st.columns(2)
        with col_stats1:
            st.metric("Percorsi trovati", stats.paths_found)
            st.metric("Percorsi processati", stats.paths_processed)
        with col_stats2:
            st.metric("Percorsi saltati", stats.paths_skipped)
            st.metric("Tempo (s)", f"{stats.processing_time:.2f}")
        
        # Parsing output
        with st.spinner("Parsing output..."):
            output_points = parse_gcode_for_visualization(output_path)
        
        # Usa stesso filtro Z dell'input
        with st.spinner("Generazione preview 3D output..."):
            fig_output = create_3d_plot(output_points, True, extrusion_only, z_range)
        
        st.plotly_chart(fig_output, use_container_width=True)
        
        # Download
        with open(output_path, "r") as f:
            output_content = f.read()
        
        st.download_button(
            label="📥 Download G-code processato",
            data=output_content,
            file_name=f"{uploaded_file.name.replace('.gcode', '')}_processed.gcode",
            mime="text/plain"
        )
        
        # Cleanup
        try:
            os.unlink(output_path)
        except:
            pass
    
    elif not uploaded_file:
        st.info("👆 Carica un file G-code per iniziare")

# Footer
st.markdown("---")
st.caption("FGF G-code Post Processor v1.0.0 - Debug UI")
