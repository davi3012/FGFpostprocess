"""
Pellet ERS - Post-processore G-code (solo flusso volumetrico).

Implementa la specifica matematica del Pellet ERS:
  1. Unita': mm/min, mm^3/min, mm^3/min^2.
  2. Volume target per riga: vol = F * |dE| / dist  [mm^3/min]
     (la E del G-code per estrusori a pellet e' gia' in mm^3: Grasshopper
     applica il filament_diameter a monte, quindi NON c'e' fattore A_f).
  3. Identificazione polilinee senza marker (run massimali di righe estrudenti).
  4. Smoothing interno (passate backward + forward) basato su
        v_end = sqrt(v_start^2 + 2 * a * dist * vol / F)
  5. Rampe di confine (ramp-up/ramp-down) ai bordi delle polilinee
     quando travel >= travel_threshold.
  6. Split trapezoidale/triangolare con interpolazione del feedrate
     (Linear, Sqrt, Exponential), ricalcolo proporzionale dell'estrusione,
     quantizzazione finale del feedrate.

Nessun marker di slicer e' richiesto: il G-code di partenza e' una sequenza
di G1 X Y (Z) E F generata da Grasshopper, con polilinee continue.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .gcode_parser import GCodeCommand, GCodeParser, write_gcode
from .smoothing import Profile, interpolate_feedrate, quantize_feedrate


# ---------------------------------------------------------------------------
# Configurazione e stato
# ---------------------------------------------------------------------------


@dataclass
class ProcessorConfig:
    """
    Parametri del Pellet ERS.

    Le pendenze sono fornite in mm^3/s^2 (unita' utente) e convertite
    internamente a mm^3/min^2 (* 3600). min_rate in mm^3/s -> mm^3/min (* 60).
    """

    # --- pendenze (input in mm^3/s^2) ---
    max_volumetric_extrusion_rate_slope: float = 1.0  # mm^3/s^2 (accel.)
    pellet_ers_deceleration_slope: float = 0.0        # mm^3/s^2 (decel.); <=0 => uguale a accel.

    # --- segmentazione e bordi ---
    max_seg_len: float = 2.0          # mm
    travel_threshold: float = 3.0     # mm (XY)

    # --- soglia inferiore di flusso al bordo (input in mm^3/s) ---
    pellet_ers_min_rate: float = 0.5  # mm^3/s

    # --- profilo della rampa di feedrate ---
    profile: Profile = Profile.SQRT

    # ----- valori derivati (in unita' interne) -----
    @property
    def slope_pos_min(self) -> float:
        """slope di accelerazione in mm^3/min^2."""
        return max(0.0, self.max_volumetric_extrusion_rate_slope) * 3600.0

    @property
    def slope_neg_min(self) -> float:
        """slope di decelerazione in mm^3/min^2; se non valido, uguale a slope_pos."""
        s = self.pellet_ers_deceleration_slope
        if s is None or s <= 0:
            return self.slope_pos_min
        return s * 3600.0

    @property
    def min_rate_min(self) -> float:
        """min rate in mm^3/min."""
        return max(0.0, self.pellet_ers_min_rate) * 60.0


@dataclass
class ProcessingStats:
    input_lines: int = 0
    output_lines: int = 0
    polylines_found: int = 0
    polylines_after_merge: int = 0
    extruding_lines: int = 0
    lines_split: int = 0
    micro_segments_emitted: int = 0
    boundary_rampups: int = 0
    boundary_rampdowns: int = 0
    processing_time: float = 0.0


# ---------------------------------------------------------------------------
# Modello interno
# ---------------------------------------------------------------------------


@dataclass
class _Line:
    """Rappresentazione interna di una riga del G-code."""
    cmd_idx: int
    kind: str  # 'extrude' | 'travel' | 'other'

    # geometria (extrude / travel)
    sx: float = 0.0
    sy: float = 0.0
    sz: float = 0.0
    ex: float = 0.0
    ey: float = 0.0
    ez: float = 0.0
    dist_xyz: float = 0.0
    dist_xy: float = 0.0
    has_z: bool = False
    dE: float = 0.0          # delta E (positivo per extrude)
    F: float = 0.0           # mm/min
    relative_e: bool = False
    relative_xyz: bool = False

    # smoothing (extrude)
    vol: float = 0.0         # mm^3/min
    rate_start: float = 0.0  # mm^3/min
    rate_end: float = 0.0    # mm^3/min


@dataclass
class _Polyline:
    first: int                  # indice in lines della prima riga 'extrude'
    last: int                   # indice in lines dell'ultima riga 'extrude'
    travel_before: float = 0.0  # mm XY prima della prima riga estrudente
    travel_after: float = 0.0   # mm XY dopo l'ultima riga estrudente


# ---------------------------------------------------------------------------
# Processore principale
# ---------------------------------------------------------------------------


class GCodeProcessor:
    """Post-processore Pellet ERS (vedi modulo docstring)."""

    def __init__(self, config: Optional[ProcessorConfig] = None):
        self.config = config or ProcessorConfig()
        self.parser = GCodeParser()
        self.stats = ProcessingStats()

    # -------- API -----------------------------------------------------------

    def process_file(self, input_path: str, output_path: str) -> ProcessingStats:
        t0 = time.time()
        self.stats = ProcessingStats()

        commands = self.parser.parse_file(input_path)
        self.stats.input_lines = len(commands)

        lines = self._build_lines(commands)
        polylines = self._detect_polylines(lines)
        self.stats.polylines_found = len(polylines)

        polylines = self._merge_polylines(polylines, lines)
        self.stats.polylines_after_merge = len(polylines)

        cfg = self.config
        for poly in polylines:
            e_idxs = self._extr_indices(lines, poly)
            if not e_idxs:
                continue
            if len(e_idxs) >= 2:
                self._backward_pass(lines, e_idxs, cfg.slope_neg_min)
                self._forward_pass(lines, e_idxs, cfg.slope_pos_min)
            if poly.travel_before >= cfg.travel_threshold:
                self._boundary_rampup(lines, e_idxs, cfg.slope_pos_min, cfg.min_rate_min)
                self.stats.boundary_rampups += 1
            if poly.travel_after >= cfg.travel_threshold:
                self._boundary_rampdown(lines, e_idxs, cfg.slope_neg_min, cfg.min_rate_min)
                self.stats.boundary_rampdowns += 1

        output_commands = self._emit(commands, lines)
        self.stats.output_lines = len(output_commands)

        write_gcode(output_commands, output_path)
        self.stats.processing_time = time.time() - t0
        return self.stats

    # -------- Build -----------------------------------------------------------

    def _build_lines(self, commands: List[GCodeCommand]) -> List[_Line]:
        # NOTA: la E del G-code per pellet e' gia' espressa in mm^3
        # (Grasshopper applica il filament_diameter a monte). Quindi non
        # esiste alcun fattore di conversione: vol = F * |dE| / dist.

        # stato macchina
        x = y = z = 0.0
        e_abs = 0.0
        f = 0.0
        rel_e = False         # modo estrusore (M82/M83)
        rel_xyz = False       # modo coordinate (G90/G91)

        out: List[_Line] = []

        for idx, cmd in enumerate(commands):
            if cmd.command == "M82":
                rel_e = False
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue
            if cmd.command == "M83":
                rel_e = True
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue
            if cmd.command == "G90":
                rel_xyz = False
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue
            if cmd.command == "G91":
                rel_xyz = True
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue
            if cmd.command == "G92":
                if "E" in cmd.params:
                    e_abs = cmd.params["E"]
                if "X" in cmd.params:
                    x = cmd.params["X"]
                if "Y" in cmd.params:
                    y = cmd.params["Y"]
                if "Z" in cmd.params:
                    z = cmd.params["Z"]
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue

            if cmd.command not in ("G0", "G1"):
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue

            # G0 / G1
            has_xyz = any(k in cmd.params for k in ("X", "Y", "Z"))
            has_e = "E" in cmd.params
            has_z = "Z" in cmd.params
            new_f = cmd.params.get("F", f)

            if not has_xyz:
                # F-only e/o E-only (retract) - non e' un movimento geometrico
                if has_e:
                    if rel_e:
                        e_abs += cmd.params["E"]
                    else:
                        e_abs = cmd.params["E"]
                if "F" in cmd.params:
                    f = new_f
                out.append(_Line(cmd_idx=idx, kind="other"))
                continue

            if rel_xyz:
                ex = x + cmd.params.get("X", 0.0)
                ey = y + cmd.params.get("Y", 0.0)
                ez = z + cmd.params.get("Z", 0.0)
            else:
                ex = cmd.params.get("X", x)
                ey = cmd.params.get("Y", y)
                ez = cmd.params.get("Z", z)

            if has_e:
                if rel_e:
                    dE = cmd.params["E"]
                    new_e = e_abs + dE
                else:
                    new_e = cmd.params["E"]
                    dE = new_e - e_abs
            else:
                dE = 0.0
                new_e = e_abs

            dx = ex - x
            dy = ey - y
            dz = ez - z
            dist_xyz = math.sqrt(dx * dx + dy * dy + dz * dz)
            dist_xy = math.sqrt(dx * dx + dy * dy)

            line = _Line(
                cmd_idx=idx,
                kind="other",
                sx=x, sy=y, sz=z,
                ex=ex, ey=ey, ez=ez,
                dist_xyz=dist_xyz,
                dist_xy=dist_xy,
                has_z=has_z,
                dE=dE if dE > 0 else 0.0,
                F=new_f,
                relative_e=rel_e,
                relative_xyz=rel_xyz,
            )

            # classifica
            if dE > 0 and dist_xy > 0 and dist_xyz > 0 and new_f > 0:
                line.kind = "extrude"
                # E e' gia' in mm^3 (estrusore a pellet, Grasshopper applica
                # filament_diameter a monte): vol = F * |dE| / dist  [mm^3/min]
                line.vol = new_f * dE / dist_xyz
                line.rate_start = line.vol
                line.rate_end = line.vol
                self.stats.extruding_lines += 1
            elif dist_xyz > 0:
                line.kind = "travel"
            else:
                line.kind = "other"

            out.append(line)

            # aggiorna stato
            x, y, z = ex, ey, ez
            e_abs = new_e
            if "F" in cmd.params:
                f = new_f

        return out

    # -------- Polylines -----------------------------------------------------

    def _detect_polylines(self, lines: List[_Line]) -> List[_Polyline]:
        polys: List[_Polyline] = []
        n = len(lines)
        i = 0
        travel_accum = 0.0
        while i < n:
            L = lines[i]
            if L.kind == "travel":
                travel_accum += L.dist_xy
                i += 1
            elif L.kind == "other":
                i += 1
            else:  # 'extrude'
                first = i
                last = i
                j = i + 1
                while j < n:
                    Lj = lines[j]
                    if Lj.kind == "extrude":
                        last = j
                        j += 1
                    elif Lj.kind == "other":
                        j += 1
                    else:
                        break
                polys.append(_Polyline(first=first, last=last, travel_before=travel_accum))
                travel_accum = 0.0
                i = j

        # travel_after per ogni polilinea
        for k, p in enumerate(polys):
            end_search = polys[k + 1].first if (k + 1) < len(polys) else n
            s = 0.0
            for j in range(p.last + 1, end_search):
                if lines[j].kind == "travel":
                    s += lines[j].dist_xy
            p.travel_after = s

        return polys

    def _merge_polylines(
        self, polylines: List[_Polyline], lines: List[_Line]
    ) -> List[_Polyline]:
        if not polylines:
            return polylines
        threshold = self.config.travel_threshold
        merged: List[_Polyline] = [polylines[0]]
        for p in polylines[1:]:
            if p.travel_before < threshold:
                # fondi nel precedente: estendi 'last' e adotta travel_after del nuovo
                prev = merged[-1]
                prev.last = p.last
                prev.travel_after = p.travel_after
            else:
                merged.append(p)
        return merged

    @staticmethod
    def _extr_indices(lines: List[_Line], poly: _Polyline) -> List[int]:
        return [i for i in range(poly.first, poly.last + 1) if lines[i].kind == "extrude"]

    # -------- Passate §5 ----------------------------------------------------

    @staticmethod
    def _backward_pass(lines: List[_Line], e_idxs: List[int], slope_neg: float) -> None:
        # da last_e_idx verso first_e_idx
        for k in range(len(e_idxs) - 2, -1, -1):
            i = e_idxs[k]
            nxt = e_idxs[k + 1]
            L = lines[i]
            Ln = lines[nxt]
            if L.F <= 0 or L.dist_xyz <= 0 or L.vol <= 0:
                continue
            cand2 = Ln.rate_start * Ln.rate_start + 2.0 * slope_neg * L.vol * L.dist_xyz / L.F
            if cand2 < 0:
                cand2 = 0.0
            cand = math.sqrt(cand2)
            if cand < L.rate_start:
                L.rate_start = cand
                if Ln.rate_start < L.rate_end:
                    L.rate_end = Ln.rate_start

    @staticmethod
    def _forward_pass(lines: List[_Line], e_idxs: List[int], slope_pos: float) -> None:
        for k in range(1, len(e_idxs)):
            i = e_idxs[k]
            prv = e_idxs[k - 1]
            L = lines[i]
            Lp = lines[prv]
            if L.F <= 0 or L.dist_xyz <= 0 or L.vol <= 0:
                continue
            cand2 = Lp.rate_end * Lp.rate_end + 2.0 * slope_pos * L.vol * L.dist_xyz / L.F
            if cand2 < 0:
                cand2 = 0.0
            cand = math.sqrt(cand2)
            if cand < L.rate_end:
                L.rate_end = cand
                if Lp.rate_end < L.rate_start:
                    L.rate_start = Lp.rate_end

    # -------- Rampe di confine §6 -------------------------------------------

    @staticmethod
    def _boundary_rampup(
        lines: List[_Line], e_idxs: List[int], slope_pos: float, min_rate: float
    ) -> None:
        if not e_idxs:
            return
        ramp_target = lines[e_idxs[0]].vol
        rate_prec = min_rate
        for i in e_idxs:
            if rate_prec >= ramp_target:
                break
            L = lines[i]
            if L.F <= 0 or L.dist_xyz <= 0 or L.vol <= 0:
                continue
            L.rate_start = rate_prec
            cand2 = rate_prec * rate_prec + 2.0 * slope_pos * L.vol * L.dist_xyz / L.F
            if cand2 < 0:
                cand2 = 0.0
            new_end = min(ramp_target, math.sqrt(cand2))
            L.rate_end = new_end
            rate_prec = new_end

    @staticmethod
    def _boundary_rampdown(
        lines: List[_Line], e_idxs: List[int], slope_neg: float, min_rate: float
    ) -> None:
        if not e_idxs:
            return
        ramp_target = lines[e_idxs[-1]].vol
        rate_succ = min_rate
        for i in reversed(e_idxs):
            if rate_succ >= ramp_target:
                break
            L = lines[i]
            if L.F <= 0 or L.dist_xyz <= 0 or L.vol <= 0:
                continue
            if rate_succ < L.rate_end:
                L.rate_end = rate_succ
            cand2 = rate_succ * rate_succ + 2.0 * slope_neg * L.vol * L.dist_xyz / L.F
            if cand2 < 0:
                cand2 = 0.0
            cand = math.sqrt(cand2)
            new_start = min(ramp_target, cand)
            if new_start < L.rate_start:
                L.rate_start = new_start
            rate_succ = L.rate_start

    # -------- Split §7 ------------------------------------------------------

    def _split_line(self, L: _Line) -> List[Dict]:
        """Restituisce una lista di micro-segmenti.

        Ogni micro-segmento e' un dict:
            {x, y, z, has_z, dE, F}
        dE e' il delta-E relativo del micro-segmento (positivo).
        F e' gia' quantizzato (multiplo di 60 mm/min, >= 60).
        """
        cfg = self.config
        slope_pos = cfg.slope_pos_min
        slope_neg = cfg.slope_neg_min
        max_seg_len = cfg.max_seg_len
        profile = cfg.profile

        l = L.dist_xyz
        vol = L.vol
        F = L.F
        rs = L.rate_start
        re = L.rate_end
        dE_total = L.dE

        # parametrizzazione XYZ
        sx, sy, sz = L.sx, L.sy, L.sz
        ex, ey, ez = L.ex, L.ey, L.ez
        has_z = L.has_z

        out: List[Dict] = []
        last_t = 0.0

        def emit(t_global_end: float, F_q: float) -> None:
            nonlocal last_t
            t_global_end = min(1.0, max(0.0, t_global_end))
            if t_global_end <= last_t:
                return
            dt = t_global_end - last_t
            x = sx + (ex - sx) * t_global_end
            y = sy + (ey - sy) * t_global_end
            z = sz + (ez - sz) * t_global_end
            dE_k = dE_total * dt
            out.append({"x": x, "y": y, "z": z, "has_z": has_z, "dE": dE_k, "F": F_q})
            last_t = t_global_end

        # --- §7.1 caso semplice ---
        near_full = (rs >= 0.98 * vol) and (re >= 0.98 * vol)
        too_short = l <= 2.0 * max_seg_len
        tiny_diff = round(abs(re - rs)) < 10
        if near_full or too_short or tiny_diff:
            avg = 0.5 * (rs + re) / vol if vol > 0 else 1.0
            avg = max(0.05, min(1.0, avg))
            F_out = quantize_feedrate(F * avg)
            emit(1.0, F_out)
            return out

        # --- §7.2 / §7.3 ---
        # lunghezze necessarie per portare il flusso a 'vol'
        l_up = max(0.0, (vol * vol - rs * rs) * F / (2.0 * slope_pos * vol)) if slope_pos > 0 else 0.0
        l_down = max(0.0, (vol * vol - re * re) * F / (2.0 * slope_neg * vol)) if slope_neg > 0 else 0.0

        if l_up + l_down <= l:
            # --- Trapezoidale ---
            l_steady = l - l_up - l_down
            # ramp-up
            if l_up >= 0.5 * max_seg_len:
                n_up = max(1, math.ceil(l_up / max_seg_len))
                f_start_up = rs * F / vol
                for k in range(1, n_up + 1):
                    t_local = k / n_up
                    t_global = t_local * (l_up / l)
                    t_mid = (k - 0.5) / n_up
                    F_mid = interpolate_feedrate(f_start_up, F, t_mid, profile)
                    emit(t_global, quantize_feedrate(F_mid))
            steady_end_t = (l_up + l_steady) / l
            # steady
            if l_steady >= 0.5 * max_seg_len:
                emit(steady_end_t, quantize_feedrate(F))
            # ramp-down
            if l_down >= 0.5 * max_seg_len:
                n_down = max(1, math.ceil(l_down / max_seg_len))
                f_end_down = re * F / vol
                for k in range(1, n_down + 1):
                    t_local = k / n_down
                    t_global = steady_end_t + t_local * (l_down / l)
                    t_mid = (k - 0.5) / n_down
                    F_mid = interpolate_feedrate(F, f_end_down, t_mid, profile)
                    emit(t_global, quantize_feedrate(F_mid))
        else:
            # --- Triangolare ---
            k_pos = 2.0 * slope_pos * vol / F if F > 0 else 0.0
            k_neg = 2.0 * slope_neg * vol / F if F > 0 else 0.0
            denom = k_pos + k_neg
            if denom > 0:
                x_meet = (re * re - rs * rs + k_neg * l) / denom
            else:
                x_meet = l * 0.5
            x_meet = max(0.0, min(l, x_meet))
            peak2 = rs * rs + k_pos * x_meet
            if peak2 < 0:
                peak2 = 0.0
            peak = min(vol, math.sqrt(peak2))
            f_peak = peak * F / vol
            f_start_up = rs * F / vol
            f_end_down = re * F / vol

            # n_up = 0 se la zona ramp-up e' troppo corta: ricade nel catch-all
            if x_meet >= 0.5 * max_seg_len:
                n_up = max(1, math.ceil(x_meet / max_seg_len))
                for k in range(1, n_up + 1):
                    t_local = k / n_up
                    t_global = t_local * (x_meet / l)
                    t_mid = (k - 0.5) / n_up
                    F_mid = interpolate_feedrate(f_start_up, f_peak, t_mid, profile)
                    emit(t_global, quantize_feedrate(F_mid))
            if (l - x_meet) >= 0.5 * max_seg_len:
                n_down = max(1, math.ceil((l - x_meet) / max_seg_len))
                for k in range(1, n_down + 1):
                    t_local = k / n_down
                    t_global = (x_meet / l) + t_local * ((l - x_meet) / l)
                    t_mid = (k - 0.5) / n_down
                    F_mid = interpolate_feedrate(f_peak, f_end_down, t_mid, profile)
                    emit(t_global, quantize_feedrate(F_mid))

        # --- catch-all ---
        # Spec §7: chiudi fino a P1 se restano > 0.01 mm su XY.
        if last_t < 1.0:
            remaining_xy = L.dist_xy * (1.0 - last_t)
            if remaining_xy > 0.01:
                emit(1.0, quantize_feedrate(F))

        # se per qualche motivo nessun micro-segmento e' stato emesso, fallback
        if not out:
            avg = 0.5 * (rs + re) / vol if vol > 0 else 1.0
            avg = max(0.05, min(1.0, avg))
            emit(1.0, quantize_feedrate(F * avg))

        return out

    # -------- Emissione -----------------------------------------------------

    def _needs_split(self, L: _Line) -> bool:
        if L.kind != "extrude" or L.vol <= 0:
            return False
        eps = 1e-6
        return (abs(L.rate_start - L.vol) > eps) or (abs(L.rate_end - L.vol) > eps)

    def _emit(
        self, commands: List[GCodeCommand], lines: List[_Line]
    ) -> List[GCodeCommand]:
        out: List[GCodeCommand] = []

        # tracking dello stato in uscita
        e_abs = 0.0
        rel_e = False
        rel_xyz = False

        last_emitted_idx = -1

        for L in lines:
            cmd_idx = L.cmd_idx
            # emetti tutti i commands tra l'ultimo emesso e questo escluso
            # (in pratica _Line copre 1:1 i commands, quindi non dovrebbe servire,
            # ma manteniamo robusto)
            for j in range(last_emitted_idx + 1, cmd_idx):
                out.append(commands[j])
            last_emitted_idx = cmd_idx
            cmd = commands[cmd_idx]

            # gestisci modalita' E e XYZ
            if cmd.command == "M82":
                rel_e = False
                out.append(cmd)
                continue
            if cmd.command == "M83":
                rel_e = True
                out.append(cmd)
                continue
            if cmd.command == "G90":
                rel_xyz = False
                out.append(cmd)
                continue
            if cmd.command == "G91":
                rel_xyz = True
                out.append(cmd)
                continue
            if cmd.command == "G92":
                if "E" in cmd.params:
                    e_abs = cmd.params["E"]
                out.append(cmd)
                continue

            if not self._needs_split(L):
                # emetti invariata; aggiorna stato E
                out.append(cmd)
                if cmd.command in ("G0", "G1") and "E" in cmd.params:
                    if rel_e:
                        e_abs += cmd.params["E"]
                    else:
                        e_abs = cmd.params["E"]
                continue

            # split
            microsegs = self._split_line(L)
            self.stats.lines_split += 1
            self.stats.micro_segments_emitted += len(microsegs)

            comment = cmd.comment
            # punto precedente in coordinate assolute (per derivare deltas in G91)
            prev_x, prev_y, prev_z = L.sx, L.sy, L.sz

            for j, ms in enumerate(microsegs):
                params: Dict[str, float] = {}
                if rel_xyz:
                    params["X"] = ms["x"] - prev_x
                    params["Y"] = ms["y"] - prev_y
                    if ms["has_z"]:
                        params["Z"] = ms["z"] - prev_z
                else:
                    params["X"] = ms["x"]
                    params["Y"] = ms["y"]
                    if ms["has_z"]:
                        params["Z"] = ms["z"]
                prev_x, prev_y, prev_z = ms["x"], ms["y"], ms["z"]

                # E
                if rel_e:
                    params["E"] = ms["dE"]
                    e_abs += ms["dE"]
                else:
                    e_abs += ms["dE"]
                    params["E"] = e_abs
                params["F"] = ms["F"]

                new_cmd = GCodeCommand(
                    line_number=0,
                    raw_line="",
                    command="G1",
                    params=params,
                    comment=comment if j == 0 else None,
                    _modified=True,
                )
                out.append(new_cmd)

        # eventuali commands rimanenti dopo l'ultimo _Line
        for j in range(last_emitted_idx + 1, len(commands)):
            out.append(commands[j])

        return out
