"""Unit tests for LoadAllocator."""

from pathlib import Path

from pnnl_load_orchestration.allocator import LoadAllocator
from pnnl_load_orchestration.schemas import (
    LoadSpec,
    OrchestrationConfig,
    VoltageBounds,
)


def test_allocator_first_feasible_success(minimal_dss_circuit: Path, tmp_path: Path):
    """Test successful allocation to the first feasible candidate bus."""
    out_dir = tmp_path / "output_model"
    # bus3 is on a higher impedance 1-phase branch and fails v_min=0.95 (drops to ~0.92 p.u.).
    # bus1 is 3-phase near source and easily accommodates the load above 0.95 p.u.
    config = OrchestrationConfig(
        model_dir=minimal_dss_circuit,
        master_file="master.dss",
        candidate_buses=["bus3", "bus1"],
        load_spec=LoadSpec(kw_total=400.0, kv_base=2.4),
        bounds=VoltageBounds(v_min=0.95, v_max=1.05),
        output_dir=out_dir,
        strategy="first_feasible",
    )

    allocator = LoadAllocator(config)
    summary = allocator.run()

    assert len(summary.evaluations) >= 2
    assert summary.success is True
    assert summary.allocated_bus == "bus1"
    assert out_dir.exists()
    assert (out_dir / "orchestrated_load_bus1.dss").exists()
    assert (out_dir / "orchestration_summary.json").exists()


def test_allocator_all_fail(minimal_dss_circuit: Path, tmp_path: Path):
    """Test case where all candidate buses exceed voltage limits."""
    out_dir = tmp_path / "output_model_fail"
    # Massive load of 50,000 kW will cause voltage collapse on all buses
    config = OrchestrationConfig(
        model_dir=minimal_dss_circuit,
        master_file="master.dss",
        candidate_buses=["bus3", "bus2"],
        load_spec=LoadSpec(kw_total=50000.0, kv_base=2.4),
        bounds=VoltageBounds(v_min=0.95, v_max=1.05),
        output_dir=out_dir,
        strategy="first_feasible",
    )

    allocator = LoadAllocator(config)
    summary = allocator.run()

    assert summary.success is False
    assert summary.allocated_bus is None
    assert all(e.violation for e in summary.evaluations)
