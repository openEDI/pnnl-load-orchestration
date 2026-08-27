"""Visualization and plotting utilities for load orchestration and network models."""

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive headless backend
import matplotlib.pyplot as plt
import numpy as np
import opendssdirect as dss
from matplotlib.collections import LineCollection

from .schemas import BusEvaluationResult, LoadSpec, VoltageBounds

logger = logging.getLogger(__name__)


def extract_bus_coordinates(model_dir: Path) -> dict[str, tuple[float, float]]:
    """Extract (X, Y) bus coordinates from OpenDSS or bus coordinate files.

    Args:
        model_dir: Directory containing OpenDSS model files.

    Returns:
        Dictionary mapping bus name (lowercase) to (x, y) coordinate tuple.
    """
    coords: dict[str, tuple[float, float]] = {}

    # Method 1: Query OpenDSS direct bus coordinates
    for bus_name in dss.Circuit.AllBusNames():
        dss.Circuit.SetActiveBus(bus_name)
        x = float(dss.Bus.X())
        y = float(dss.Bus.Y())
        if x != 0.0 or y != 0.0:
            coords[bus_name.lower()] = (x, y)

    if coords:
        return coords

    # Method 2: Inspect potential coordinate files (*busxy*.dss, *buscoord*.dss, *.dat)
    coord_patterns = ["*busxy*.dss", "*buscoords*.dss", "*bus_xy*.dss", "*.dat"]
    for pattern in coord_patterns:
        for f in model_dir.glob(pattern):
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or line.startswith("//") or line.startswith("!"):
                        continue
                    parts = [p.strip() for p in line.replace(",", " ").split()]
                    if len(parts) >= 3:
                        try:
                            b_name = parts[0].lower()
                            bx = float(parts[1])
                            by = float(parts[2])
                            coords[b_name] = (bx, by)
                        except ValueError:
                            continue
            except Exception as e:
                logger.debug("Failed reading coordinate file %s: %e", f, e)

    return coords


def plot_feeder_voltage_heatmap(
    model_dir: Path,
    evaluations: list[BusEvaluationResult],
    selected_bus: str | None,
    load_spec: LoadSpec,
    bounds: VoltageBounds,
    voltages: dict[str, float],
    output_path: Path,
) -> Path:
    """Plot distribution feeder network map with lines and buses heatmapped by voltage magnitude.

    Args:
        model_dir: Path to model directory.
        evaluations: List of candidate bus evaluations.
        selected_bus: ID of the selected/allocated candidate bus.
        load_spec: Load specification added.
        bounds: Voltage boundary constraints.
        voltages: Per-node voltage dictionary from circuit power flow.
        output_path: Destination path for saved image.

    Returns:
        Resolved Path to saved plot.
    """
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coords = extract_bus_coordinates(model_dir)

    fig, ax = plt.subplots(figsize=(13, 11))

    # Compute bus-level average voltages
    bus_voltages: dict[str, float] = {}
    for bus_name in dss.Circuit.AllBusNames():
        b_key = bus_name.lower()
        node_vals = [v for n, v in voltages.items() if n.lower().startswith(f"{b_key}.")]
        if node_vals:
            bus_voltages[b_key] = float(np.mean(node_vals))
        else:
            bus_voltages[b_key] = 1.0

    # Colormap and normalization for line voltages (Turbo colormap for rich spectrum)
    v_min_scale = min(bounds.v_min - 0.01, 0.94)
    v_max_scale = max(bounds.v_max + 0.01, 1.06)
    norm = matplotlib.colors.Normalize(vmin=v_min_scale, vmax=v_max_scale)
    cmap = plt.cm.turbo

    # Plot network lines if bus coordinates exist
    if coords:
        segments = []
        line_v_mags = []

        # Lines
        for line_name in dss.Lines.AllNames():
            dss.Lines.Name(line_name)
            b1 = dss.Lines.Bus1().split(".")[0].lower()
            b2 = dss.Lines.Bus2().split(".")[0].lower()
            if b1 in coords and b2 in coords:
                segments.append([(coords[b1][0], coords[b1][1]), (coords[b2][0], coords[b2][1])])
                v_avg = (bus_voltages.get(b1, 1.0) + bus_voltages.get(b2, 1.0)) / 2.0
                line_v_mags.append(v_avg)

        # Transformers
        for xfmr_name in dss.Transformers.AllNames():
            dss.Transformers.Name(xfmr_name)
            dss.Circuit.SetActiveElement(f"Transformer.{xfmr_name}")
            buses = dss.CktElement.BusNames()
            if len(buses) >= 2:
                b1 = buses[0].split(".")[0].lower()
                b2 = buses[1].split(".")[0].lower()
                if b1 in coords and b2 in coords:
                    segments.append([(coords[b1][0], coords[b1][1]), (coords[b2][0], coords[b2][1])])
                    v_avg = (bus_voltages.get(b1, 1.0) + bus_voltages.get(b2, 1.0)) / 2.0
                    line_v_mags.append(v_avg)

        # Draw heatmapped lines
        if segments:
            lc = LineCollection(segments, cmap=cmap, norm=norm, linewidth=2.8, zorder=2, alpha=0.9)
            lc.set_array(np.array(line_v_mags))
            ax.add_collection(lc)

        # Plot feeder bus scatter points heatmapped by voltage
        bus_x = [coords[b][0] for b in coords if b in bus_voltages]
        bus_y = [coords[b][1] for b in coords if b in bus_voltages]
        bus_c = [bus_voltages[b] for b in coords if b in bus_voltages]
        sc = ax.scatter(
            bus_x,
            bus_y,
            c=bus_c,
            cmap=cmap,
            norm=norm,
            s=32,
            edgecolors="#2c3e50",
            linewidth=0.5,
            zorder=3,
            label="Feeder Buses",
        )

        # Colorbar
        cbar = fig.colorbar(lc if segments else sc, ax=ax, orientation="vertical", pad=0.02, shrink=0.85)
        cbar.set_label("Nodal / Line Voltage Magnitude (p.u.)", fontsize=11, fontweight="bold")
        cbar.ax.axhline(bounds.v_min, color="red", linestyle="--", linewidth=1.5)
        cbar.ax.axhline(bounds.v_max, color="red", linestyle="--", linewidth=1.5)

        # Auto-scale axes to coordinates
        all_x = [c[0] for c in coords.values()]
        all_y = [c[1] for c in coords.values()]
        pad_x = (max(all_x) - min(all_x)) * 0.05
        pad_y = (max(all_y) - min(all_y)) * 0.05
        ax.set_xlim(min(all_x) - pad_x, max(all_x) + pad_x)
        ax.set_ylim(min(all_y) - pad_y, max(all_y) + pad_y)

    else:
        ax.text(
            0.5,
            0.5,
            "Coordinates not available in model;\nCandidate list shown in legend.",
            horizontalalignment="center",
            verticalalignment="center",
            transform=ax.transAxes,
            fontsize=12,
            color="#7f8c8d",
        )

    # Overlay candidate buses
    for e in evaluations:
        b_key = e.bus_id.lower()
        if coords and b_key in coords:
            pos = coords[b_key]
            if e.violation:
                ax.scatter(pos[0], pos[1], c="#e74c3c", s=180, edgecolors="black", linewidth=2.0, zorder=5)
                ax.annotate(
                    f"Bus {e.bus_id}\n({e.min_voltage:.3f} pu - Viol)",
                    (pos[0], pos[1]),
                    textcoords="offset points",
                    xytext=(0, 12),
                    ha="center",
                    fontsize=8.5,
                    fontweight="bold",
                    color="#900c3f",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#fadbd8", ec="#e74c3c", alpha=0.95),
                    zorder=6,
                )
            else:
                ax.scatter(pos[0], pos[1], c="#2ecc71", s=180, edgecolors="black", linewidth=2.0, zorder=5)
                ax.annotate(
                    f"Bus {e.bus_id}\n({e.min_voltage:.3f} pu - OK)",
                    (pos[0], pos[1]),
                    textcoords="offset points",
                    xytext=(0, 12),
                    ha="center",
                    fontsize=8.5,
                    fontweight="bold",
                    color="#196f3d",
                    bbox=dict(boxstyle="round,pad=0.25", fc="#d4efdf", ec="#2ecc71", alpha=0.95),
                    zorder=6,
                )

    # Prominently highlight selected allocated bus
    if selected_bus is not None and coords and selected_bus.lower() in coords:
        sel_pos = coords[selected_bus.lower()]
        ax.scatter(
            sel_pos[0],
            sel_pos[1],
            c="#f39c12",
            s=450,
            marker="*",
            edgecolors="#935116",
            linewidth=2.5,
            zorder=7,
            label=f"Selected Allocation: Bus {selected_bus}",
        )
        ax.annotate(
            f"★ SELECTED: Bus {selected_bus}\n+{load_spec.kw_total:g} kW ({load_spec.conn})",
            (sel_pos[0], sel_pos[1]),
            textcoords="offset points",
            xytext=(20, -30),
            ha="left",
            fontsize=10.5,
            fontweight="bold",
            color="#78281f",
            bbox=dict(boxstyle="round,pad=0.4", fc="#fdebd0", ec="#e67e22", lw=2, alpha=0.95),
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.2", color="#d35400", lw=2.2),
            zorder=8,
        )

    # Legend elements
    handles, labels = ax.get_legend_handles_labels()
    handles.append(
        plt.Line2D(
            [0], [0], marker="o", color="w", markerfacecolor="#e74c3c", markersize=10, label="Violation Candidate"
        )
    )
    handles.append(
        plt.Line2D(
            [0], [0], marker="o", color="w", markerfacecolor="#2ecc71", markersize=10, label="Compliant Candidate"
        )
    )
    ax.legend(handles=handles, loc="upper right", framealpha=0.95)

    ax.set_title(
        f"Distribution Feeder Voltage Heatmap & Load Allocation\n"
        f"Target Load: {load_spec.kw_total:g} kW | Allocated Bus: {selected_bus or 'None'}",
        fontsize=14,
        fontweight="bold",
        pad=15,
    )
    ax.set_xlabel("X Coordinate (ft / relative)", fontsize=11)
    ax.set_ylabel("Y Coordinate (ft / relative)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.3)
    plt.tight_layout()

    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved feeder voltage heatmap to: %s", output_path)
    return output_path


# Alias for backward compatibility
plot_feeder_map = plot_feeder_voltage_heatmap


def plot_voltage_profiles(
    base_voltages: dict[str, float],
    final_voltages: dict[str, float],
    bounds: VoltageBounds,
    selected_bus: str | None,
    output_path: Path,
) -> Path:
    """Plot before-and-after voltage profile scatter with ANSI C84.1 limit lines.

    Args:
        base_voltages: Node voltages before load placement.
        final_voltages: Node voltages after load placement.
        bounds: Voltage boundary constraints.
        selected_bus: Chosen bus identifier.
        output_path: Destination path for plot.

    Returns:
        Resolved Path to saved plot.
    """
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Align node keys
    nodes = sorted(list(set(base_voltages.keys()) | set(final_voltages.keys())))
    if not nodes:
        return output_path

    node_idx = np.arange(len(nodes))
    v_base = np.array([base_voltages.get(n, 1.0) for n in nodes])
    v_final = np.array([final_voltages.get(n, 1.0) for n in nodes])

    fig, ax = plt.subplots(figsize=(13, 5))

    # Base profile
    ax.scatter(node_idx, v_base, color="#3498db", s=18, alpha=0.6, label="Base Voltage (No Extra Load)", zorder=2)

    # Final profile
    out_of_limits = (v_final < bounds.v_min) | (v_final > bounds.v_max)
    ax.scatter(
        node_idx[~out_of_limits],
        v_final[~out_of_limits],
        color="#27ae60",
        s=26,
        edgecolors="black",
        linewidth=0.5,
        label="Orchestrated (Within Limits)",
        zorder=3,
    )
    if np.any(out_of_limits):
        ax.scatter(
            node_idx[out_of_limits],
            v_final[out_of_limits],
            color="#e74c3c",
            s=36,
            edgecolors="black",
            linewidth=0.8,
            label="Orchestrated (Violation)",
            zorder=4,
        )

    # Boundary lines
    ax.axhline(
        bounds.v_max, color="#c0392b", linestyle="--", linewidth=1.5, label=f"Vmax Limit ({bounds.v_max:.2f} pu)"
    )
    ax.axhline(
        bounds.v_min, color="#c0392b", linestyle="--", linewidth=1.5, label=f"Vmin Limit ({bounds.v_min:.2f} pu)"
    )
    ax.axhline(1.0, color="#7f8c8d", linestyle=":", linewidth=1.0, alpha=0.7)

    y_min_val = min(np.min(v_base), np.min(v_final), bounds.v_min - 0.02)
    y_max_val = max(np.max(v_base), np.max(v_final), bounds.v_max + 0.02)
    ax.set_ylim(y_min_val - 0.01, y_max_val + 0.01)
    ax.set_xlim(-1, len(nodes))

    ax.set_title(
        f"Distribution Feeder Voltage Profile Comparison (Base vs. Orchestrated)\n"
        f"Allocated Bus: {selected_bus or 'None'} | Total Nodes Evaluated: {len(nodes)}",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )
    ax.set_xlabel("Feeder Node Index", fontsize=11)
    ax.set_ylabel("Nodal Voltage Magnitude (p.u.)", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="lower right", framealpha=0.95)

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved voltage profile comparison to: %s", output_path)
    return output_path
