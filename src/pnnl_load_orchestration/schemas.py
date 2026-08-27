"""Pydantic schemas and configuration models for load orchestration."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class LoadSpec(BaseModel):
    """Specification of the additional load to be orchestrated.

    Attributes:
        kw_total: Total active power in kW to be split across phases.
        kvar_total: Total reactive power in kvar to be split across phases.
        kv_base: Voltage base (line-to-neutral or line-to-line depending on connection) in kV.
        conn: Connection type ('Wye' or 'Delta').
        model_type: OpenDSS load model (e.g. 1 = constant PQ).
        load_name_prefix: Prefix string for generated load object names in OpenDSS.
    """

    kw_total: float = Field(gt=0, description="Total active power (kW) to allocate")
    kvar_total: float = Field(default=0.0, ge=0, description="Total reactive power (kvar) to allocate")
    kv_base: float = Field(default=2.4, gt=0, description="Base voltage in kV (e.g. 2.4 kV for 4.16 kV Wye system)")
    conn: Literal["Wye", "Delta"] = Field(default="Wye", description="Load connection type")
    model_type: int = Field(default=1, description="OpenDSS Load model type (1=const PQ)")
    load_name_prefix: str = Field(default="DC", description="Prefix for allocated load element names")


class VoltageBounds(BaseModel):
    """Voltage boundary constraints in per-unit (p.u.).

    Attributes:
        v_min: Minimum allowable per-unit voltage (default 0.95 ANSI C84.1).
        v_max: Maximum allowable per-unit voltage (default 1.05 ANSI C84.1).
    """

    v_min: float = Field(default=0.95, gt=0, description="Minimum acceptable voltage in p.u.")
    v_max: float = Field(default=1.05, gt=0, description="Maximum acceptable voltage in p.u.")

    @model_validator(mode="after")
    def validate_bounds(self) -> "VoltageBounds":
        """Ensure v_min is strictly less than v_max."""
        if self.v_min >= self.v_max:
            raise ValueError(f"v_min ({self.v_min}) must be strictly less than v_max ({self.v_max})")
        return self


class ComponentParameters(BaseModel):
    """Primary configuration model and OEDISI ComponentParameters for load orchestration.

    Attributes:
        name: Optional component or scenario name.
        model_dir: Directory containing OpenDSS model files.
        master_file: Name of the master OpenDSS file.
        candidate_buses: List of candidate bus IDs to evaluate.
        load_spec: Specification of the load to place.
        bounds: Voltage boundary constraints.
        bus_phases: Optional explicit mapping of bus ID to active phase list [1, 2, 3].
                    If omitted, phases are discovered dynamically from the circuit.
        output_dir: Optional destination directory for modified OpenDSS files.
        in_place: Whether to modify source files in place (mutually exclusive with output_dir).
        strategy: Candidate evaluation strategy ('first_feasible', 'evaluate_all', 'rank_by_margin').
        plot_results: Whether to generate plots (feeder map, candidate heatmap, voltage profile).
    """

    name: str | None = Field(default=None, description="Optional component/scenario name")
    model_dir: Path = Field(description="Path to OpenDSS model directory")
    master_file: str = Field(default="master.dss", description="Master DSS file name")
    candidate_buses: list[str] = Field(min_length=1, description="Candidate bus IDs in evaluation order")
    load_spec: LoadSpec = Field(description="Load specification")
    bounds: VoltageBounds = Field(default_factory=VoltageBounds, description="Voltage bounds")
    bus_phases: dict[str, list[int]] | None = Field(
        default=None,
        description="Optional manual bus to phases mapping (e.g. {'47': [1, 2, 3], '83': [3]})",
    )
    output_dir: Path | None = Field(default=None, description="Output directory for modified OpenDSS files")
    in_place: bool = Field(default=False, description="Modify OpenDSS model in place")
    strategy: Literal["first_feasible", "evaluate_all", "rank_by_margin"] = Field(
        default="first_feasible",
        description="Evaluation strategy",
    )
    plot_results: bool = Field(default=True, description="Generate visualizations and candidate heatmaps")

    @field_validator("candidate_buses", mode="before")
    @classmethod
    def stringify_candidate_buses(cls, v: list[str | int]) -> list[str]:
        """Normalize all candidate buses to strings."""
        return [str(item) for item in v]

    @field_validator("model_dir", "output_dir", mode="after")
    @classmethod
    def resolve_paths(cls, v: Path | None) -> Path | None:
        """Resolve paths to absolute paths."""
        if v is not None:
            return v.expanduser().resolve()
        return None

    @model_validator(mode="after")
    def validate_io_targets(self) -> "ComponentParameters":
        """Validate input directory exists and output configuration is valid."""
        if not self.model_dir.exists():
            raise ValueError(f"model_dir does not exist: {self.model_dir}")
        master_path = self.model_dir / self.master_file
        if not master_path.exists():
            # Check case-insensitive alternative
            matches = [f for f in self.model_dir.iterdir() if f.name.lower() == self.master_file.lower()]
            if matches:
                self.master_file = matches[0].name
            else:
                raise ValueError(f"Master file '{self.master_file}' not found in '{self.model_dir}'")

        if self.in_place and self.output_dir is not None:
            raise ValueError("Cannot specify both in_place=True and output_dir simultaneously")

        return self

    @classmethod
    def generate_json_schema(cls, target_path: Path) -> Path:
        """Generate schema.json file from ComponentParameters.

        Args:
            target_path: Path to write schema.json.

        Returns:
            Resolved Path of written schema.
        """
        target_path = target_path.resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        schema_dict = cls.model_json_schema()
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(schema_dict, f, indent=2)
            f.write("\n")
        return target_path


# Alias for backward compatibility
OrchestrationConfig = ComponentParameters


class BusEvaluationResult(BaseModel):
    """Result of evaluating a single candidate bus.

    Attributes:
        bus_id: Identifier of the bus evaluated.
        phases: List of phases tested on this bus.
        violation: True if any node voltage violated the voltage bounds.
        min_voltage: Minimum observed node voltage across the entire system.
        max_voltage: Maximum observed node voltage across the entire system.
        violating_nodes: List of node names (e.g. '83.3') that violated bounds.
    """

    bus_id: str
    phases: list[int]
    violation: bool
    min_voltage: float
    max_voltage: float
    violating_nodes: list[str] = Field(default_factory=list)


class OrchestrationSummary(BaseModel):
    """Summary of the full load orchestration run.

    Attributes:
        success: True if a feasible bus was found and configured.
        allocated_bus: The bus ID selected for final allocation (if successful).
        load_spec: The load specification that was applied.
        evaluations: List of evaluations for all tested candidate buses.
        output_directory: Directory where modified model or results are stored.
        generated_files: List of generated or modified DSS and image file paths.
    """

    success: bool
    allocated_bus: str | None = None
    load_spec: LoadSpec
    evaluations: list[BusEvaluationResult] = Field(default_factory=list)
    output_directory: str | None = None
    generated_files: list[str] = Field(default_factory=list)
