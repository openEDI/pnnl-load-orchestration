"""Core load allocation and constraint checking orchestrator."""

import logging

from .dss_engine import OpenDSSEngine
from .io import append_load_to_master, prepare_output_directory, save_summary, write_load_definitions
from .plotting import plot_feeder_voltage_heatmap, plot_voltage_profiles
from .schemas import (
    BusEvaluationResult,
    ComponentParameters,
    OrchestrationSummary,
)

logger = logging.getLogger(__name__)


class LoadAllocator:
    """Orchestrates candidate bus evaluation, constraint checking, and OpenDSS model updates."""

    def __init__(self, config: ComponentParameters) -> None:
        """Initialize the LoadAllocator with configuration.

        Args:
            config: ComponentParameters / OrchestrationConfig instance.
        """
        self.config = config

    def run(self) -> OrchestrationSummary:
        """Execute the load orchestration workflow.

        Returns:
            OrchestrationSummary detailing candidate evaluations and modified files.
        """
        # Determine working directory
        if self.config.output_dir is not None:
            work_dir = prepare_output_directory(self.config.model_dir, self.config.output_dir)
        else:
            work_dir = self.config.model_dir

        master_path = work_dir / self.config.master_file
        engine = OpenDSSEngine(master_path)
        engine.compile()

        # Capture base voltage profile
        base_voltages = engine.extract_nodal_voltages()

        evaluations: list[BusEvaluationResult] = []
        selected_bus: str | None = None
        selected_phases: list[int] = []

        logger.info(
            "Beginning evaluation of %d candidate buses with %g kW load (strategy=%s)...",
            len(self.config.candidate_buses),
            self.config.load_spec.kw_total,
            self.config.strategy,
        )

        for bus_id in self.config.candidate_buses:
            bus_str = str(bus_id)

            # Determine phases for this bus
            if self.config.bus_phases and bus_str in self.config.bus_phases:
                phases = self.config.bus_phases[bus_str]
            else:
                phases = engine.discover_bus_phases(bus_str)

            logger.info("Evaluating candidate Bus %s on phases %s...", bus_str, phases)

            # Inject candidate load
            created_loads = engine.add_load(bus_str, phases, self.config.load_spec)

            # Solve power flow
            converged = engine.solve()
            if not converged:
                logger.warning("Power flow diverged when testing Bus %s.", bus_str)
                evaluations.append(
                    BusEvaluationResult(
                        bus_id=bus_str,
                        phases=phases,
                        violation=True,
                        min_voltage=0.0,
                        max_voltage=0.0,
                        violating_nodes=["DIVERGENCE"],
                    )
                )
                engine.remove_load(created_loads)
                continue

            # Extract nodal voltages and evaluate bounds
            voltages = engine.extract_nodal_voltages()
            has_violation, min_v, max_v, violating_nodes = engine.check_voltage_violations(voltages, self.config.bounds)

            eval_res = BusEvaluationResult(
                bus_id=bus_str,
                phases=phases,
                violation=has_violation,
                min_voltage=min_v,
                max_voltage=max_v,
                violating_nodes=violating_nodes,
            )
            evaluations.append(eval_res)

            if has_violation:
                logger.info(
                    "Bus %s failed: Voltage violation detected (min: %.4f p.u., max: %.4f p.u., %d violating nodes).",
                    bus_str,
                    min_v,
                    max_v,
                    len(violating_nodes),
                )
                engine.remove_load(created_loads)
            else:
                logger.info(
                    "Bus %s succeeded: No voltage violations (min: %.4f p.u., max: %.4f p.u.).",
                    bus_str,
                    min_v,
                    max_v,
                )
                if self.config.strategy == "first_feasible":
                    selected_bus = bus_str
                    selected_phases = phases
                    break
                # If evaluating all, remove and continue
                engine.remove_load(created_loads)

        # Handle other strategies if first_feasible was not used
        if self.config.strategy in ["evaluate_all", "rank_by_margin"] and not selected_bus:
            feasible_evals = [e for e in evaluations if not e.violation]
            if feasible_evals:
                # Rank by highest minimum voltage (furthest from lower bound)
                best_eval = max(feasible_evals, key=lambda e: e.min_voltage)
                selected_bus = best_eval.bus_id
                selected_phases = best_eval.phases

        generated_files: list[str] = []

        if selected_bus is not None:
            logger.info("Successfully selected Bus %s for load allocation.", selected_bus)
            # Write load definition file
            load_filename = f"orchestrated_load_{selected_bus}.dss"
            load_dss_path = work_dir / load_filename
            write_load_definitions(
                load_dss_path,
                selected_bus,
                selected_phases,
                self.config.load_spec,
            )
            generated_files.append(str(load_dss_path))

            # Modify master DSS
            append_load_to_master(master_path, load_filename)
            generated_files.append(str(master_path))

            # Recompile to extract final voltage profile
            engine.compile()
            final_voltages = engine.extract_nodal_voltages()

            summary = OrchestrationSummary(
                success=True,
                allocated_bus=selected_bus,
                load_spec=self.config.load_spec,
                evaluations=evaluations,
                output_directory=str(work_dir),
                generated_files=generated_files,
            )
        else:
            logger.warning("No candidate bus satisfied the voltage constraints.")
            final_voltages = base_voltages
            summary = OrchestrationSummary(
                success=False,
                allocated_bus=None,
                load_spec=self.config.load_spec,
                evaluations=evaluations,
                output_directory=str(work_dir),
                generated_files=[],
            )

        # Generate plots if requested
        if self.config.plot_results:
            try:
                map_path = work_dir / "feeder_voltage_heatmap.png"
                profile_path = work_dir / "voltage_profile_comparison.png"

                plot_feeder_voltage_heatmap(
                    self.config.model_dir,
                    evaluations,
                    selected_bus,
                    self.config.load_spec,
                    self.config.bounds,
                    final_voltages,
                    map_path,
                )
                plot_voltage_profiles(
                    base_voltages,
                    final_voltages,
                    self.config.bounds,
                    selected_bus,
                    profile_path,
                )

                summary.generated_files.extend([str(map_path), str(profile_path)])
            except Exception as plot_err:
                logger.warning("Failed generating visual plots: %s", plot_err)

        # Write summary JSON
        summary_path = work_dir / "orchestration_summary.json"
        save_summary(summary_path, summary)
        summary.generated_files.append(str(summary_path))

        return summary
