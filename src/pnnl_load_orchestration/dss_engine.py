"""OpenDSS engine interface and power flow utilities."""

import logging
import os
from pathlib import Path

import opendssdirect as dss

from .schemas import LoadSpec, VoltageBounds

logger = logging.getLogger(__name__)


class OpenDSSEngine:
    """Encapsulates interaction with OpenDSSDirect for circuit simulation and modification."""

    def __init__(self, master_path: Path) -> None:
        """Initialize the OpenDSS engine.

        Args:
            master_path: Absolute path to the master DSS file.
        """
        self.master_path = master_path.resolve()
        self.working_dir = self.master_path.parent

    def compile(self) -> None:
        """Compile the master OpenDSS circuit and solve initial state."""
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            logger.info("Compiling OpenDSS model: %s", self.master_path)
            dss.Text.Command("Clear")
            compile_cmd = f"Compile ({self.master_path.name})"
            dss.Text.Command(compile_cmd)
            dss.Solution.Solve()
            if not dss.Solution.Converged():
                logger.warning("Base circuit power flow did not converge on initial solve.")
        finally:
            os.chdir(original_cwd)

    def solve(self) -> bool:
        """Solve power flow.

        Returns:
            True if solution converged, False otherwise.
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            dss.Solution.Solve()
            converged = bool(dss.Solution.Converged())
            if not converged:
                logger.warning("Power flow solution did not converge.")
            return converged
        finally:
            os.chdir(original_cwd)

    def discover_bus_phases(self, bus_id: str) -> list[int]:
        """Discover connected phases for a given bus ID.

        Args:
            bus_id: Bus identifier string.

        Returns:
            List of phase integers (e.g. [1, 2, 3] or [3]).
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            # Method 1: Check active bus nodes in OpenDSS
            dss.Circuit.SetActiveBus(str(bus_id))
            nodes = list(dss.Bus.Nodes())
            if nodes and all(n in [1, 2, 3] for n in nodes):
                return sorted(nodes)

            # Method 2: Inspect AllNodeNames
            all_nodes = dss.Circuit.AllNodeNames()
            phases: list[int] = []
            for p in [1, 2, 3]:
                target = f"{bus_id}.{p}"
                if target.lower() in [n.lower() for n in all_nodes]:
                    phases.append(p)

            if phases:
                return sorted(phases)

            # Default fallback to 3-phase if no specific node suffixes found
            logger.debug("No specific phase nodes found for bus %s, defaulting to [1, 2, 3]", bus_id)
            return [1, 2, 3]
        finally:
            os.chdir(original_cwd)

    def extract_nodal_voltages(self) -> dict[str, float]:
        """Extract all node voltages in per-unit (p.u.).

        Returns:
            Dictionary mapping node names (e.g. '83.3') to p.u. voltage magnitude.
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            node_names = dss.Circuit.AllNodeNames()
            node_a: list[str] = []
            node_b: list[str] = []
            node_c: list[str] = []
            for node in node_names:
                if ".1" in node:
                    node_a.append(node)
                elif ".2" in node:
                    node_b.append(node)
                elif ".3" in node:
                    node_c.append(node)

            bus_voltages: dict[str, float] = {}
            for p, phase_nodes in [(1, node_a), (2, node_b), (3, node_c)]:
                vmag_pu = dss.Circuit.AllNodeVmagPUByPhase(p)
                for idx, v in enumerate(vmag_pu):
                    if idx < len(phase_nodes):
                        bus_voltages[phase_nodes[idx]] = float(v)

            # Fallback if phase-specific extraction returned empty
            if not bus_voltages:
                # Try generic bus mag pu
                for bus_name in dss.Circuit.AllBusNames():
                    dss.Circuit.SetActiveBus(bus_name)
                    nodes = dss.Bus.Nodes()
                    # PuVoltage returns pairs of [real, imag] or magnitudes
                    v_mags = dss.Bus.VMagAngle()
                    kv_base = dss.Bus.kVBase()
                    if kv_base > 0 and len(v_mags) >= 2:
                        for idx, node_num in enumerate(nodes):
                            mag = v_mags[2 * idx] if 2 * idx < len(v_mags) else 0.0
                            pu = mag / (kv_base * 1000.0)
                            bus_voltages[f"{bus_name}.{node_num}"] = float(pu)

            return bus_voltages
        finally:
            os.chdir(original_cwd)

    def check_voltage_violations(
        self,
        voltages: dict[str, float],
        bounds: VoltageBounds,
    ) -> tuple[bool, float, float, list[str]]:
        """Check for voltage bound violations across all extracted node voltages.

        Args:
            voltages: Mapping of node name to per-unit voltage.
            bounds: VoltageBounds specifying v_min and v_max.

        Returns:
            Tuple of (has_violation, min_voltage, max_voltage, violating_node_names).
        """
        if not voltages:
            return False, 1.0, 1.0, []

        min_v = min(voltages.values())
        max_v = max(voltages.values())
        violating_nodes = [node for node, v in voltages.items() if v < bounds.v_min or v > bounds.v_max]
        has_violation = len(violating_nodes) > 0
        return has_violation, min_v, max_v, violating_nodes

    def add_load(self, bus_id: str, phases: list[int], load_spec: LoadSpec) -> list[str]:
        """Add new load objects across specified phases of candidate bus.

        Args:
            bus_id: Target bus ID.
            phases: List of phases to connect load to.
            load_spec: Load specification.

        Returns:
            List of generated OpenDSS load object names.
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            num_phases = len(phases) if phases else 1
            kw_per_phase = load_spec.kw_total / num_phases
            kvar_per_phase = load_spec.kvar_total / num_phases

            created_load_names: list[str] = []
            for ph in phases:
                load_name = f"{load_spec.load_name_prefix}_{bus_id}_ph{ph}"
                cmd = (
                    f"New Load.{load_name} Bus1={bus_id}.{ph} Phases=1 "
                    f"Conn={load_spec.conn} Model={load_spec.model_type} "
                    f"kV={load_spec.kv_base} kW={kw_per_phase:.4f} kvar={kvar_per_phase:.4f}"
                )
                logger.debug("Executing OpenDSS command: %s", cmd)
                dss.Text.Command(cmd)
                created_load_names.append(load_name)

            return created_load_names
        finally:
            os.chdir(original_cwd)

    def remove_load(self, load_names: list[str]) -> None:
        """Disable or remove previously added load elements.

        Args:
            load_names: List of OpenDSS load names to disable.
        """
        original_cwd = os.getcwd()
        try:
            os.chdir(self.working_dir)
            for name in load_names:
                cmd = f"Disable Load.{name}"
                logger.debug("Executing OpenDSS command: %s", cmd)
                dss.Text.Command(cmd)
        finally:
            os.chdir(original_cwd)
