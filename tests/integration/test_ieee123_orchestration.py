"""Integration tests with IEEE 123-bus test feeder."""

from pathlib import Path

import opendssdirect as dss
import pytest

from pnnl_load_orchestration.allocator import LoadAllocator
from pnnl_load_orchestration.schemas import (
    LoadSpec,
    OrchestrationConfig,
    VoltageBounds,
)


@pytest.mark.integration
def test_ieee123_load_orchestration(ieee123_model_dir: Path, tmp_path: Path):
    """Test end-to-end load orchestration against the IEEE 123-bus test feeder."""
    output_dir = tmp_path / "ieee123_orchestrated"

    # Candidate buses matching load_orchestration_v0.py: [83, 65, 47, 48, 76]
    # In IEEE 123, placing 1700 kW at bus 83, 65, 47, or 48 induces voltage constraint
    # violations (either under-voltage or regulator tap boost over-voltage at downstream nodes).
    # Candidate bus 76 accommodates the load without violating bounds [0.95, 1.05].
    config = OrchestrationConfig(
        model_dir=ieee123_model_dir,
        master_file="IEEE123Master.dss",
        candidate_buses=["83", "65", "47", "48", "76"],
        load_spec=LoadSpec(
            kw_total=1700.0,
            kvar_total=0.0,
            kv_base=2.4,
            conn="Wye",
            model_type=1,
            load_name_prefix="DC",
        ),
        bounds=VoltageBounds(v_min=0.95, v_max=1.05),
        output_dir=output_dir,
        strategy="first_feasible",
    )

    allocator = LoadAllocator(config)
    summary = allocator.run()

    # Verify execution summary
    assert summary.success is True
    assert summary.allocated_bus in ["65", "47", "48", "76"]
    assert len(summary.evaluations) >= 2

    # Verify Bus 83 failed with voltage violation
    bus83_eval = next((e for e in summary.evaluations if e.bus_id == "83"), None)
    assert bus83_eval is not None
    assert bus83_eval.violation is True
    assert bus83_eval.min_voltage < 0.95 or bus83_eval.max_voltage > 1.05

    # Verify allocated bus evaluation succeeded
    allocated_eval = next((e for e in summary.evaluations if e.bus_id == summary.allocated_bus), None)
    assert allocated_eval is not None
    assert allocated_eval.violation is False
    assert allocated_eval.min_voltage >= 0.95
    assert allocated_eval.max_voltage <= 1.05

    # Verify output model directory was created with necessary DSS files
    assert output_dir.exists()
    master_dss_path = output_dir / "IEEE123Master.dss"
    load_dss_path = output_dir / f"orchestrated_load_{summary.allocated_bus}.dss"
    summary_json_path = output_dir / "orchestration_summary.json"

    assert master_dss_path.exists()
    assert load_dss_path.exists()
    assert summary_json_path.exists()

    # Verify that the generated output model compiles and solves cleanly
    dss.Text.Command("Clear")
    dss.Text.Command(f"Compile ({master_dss_path})")
    dss.Solution.Solve()
    assert bool(dss.Solution.Converged()) is True
