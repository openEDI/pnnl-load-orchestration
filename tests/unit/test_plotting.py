"""Unit tests for plotting and visualization functions."""

from pathlib import Path

from pnnl_load_orchestration.plotting import (
    plot_feeder_voltage_heatmap,
    plot_voltage_profiles,
)
from pnnl_load_orchestration.schemas import (
    BusEvaluationResult,
    LoadSpec,
    VoltageBounds,
)


def test_plot_feeder_voltage_heatmap(minimal_dss_circuit: Path, tmp_path: Path):
    """Test generating distribution feeder voltage heatmap."""
    out_png = tmp_path / "test_feeder_heatmap.png"
    evaluations = [
        BusEvaluationResult(
            bus_id="bus3",
            phases=[3],
            violation=True,
            min_voltage=0.92,
            max_voltage=1.01,
            violating_nodes=["bus3.3"],
        ),
        BusEvaluationResult(
            bus_id="bus1",
            phases=[1, 2, 3],
            violation=False,
            min_voltage=0.99,
            max_voltage=1.00,
            violating_nodes=[],
        ),
    ]
    load_spec = LoadSpec(kw_total=400.0, kv_base=2.4)
    bounds = VoltageBounds(v_min=0.95, v_max=1.05)
    voltages = {"bus1.1": 0.998, "bus1.2": 0.998, "bus1.3": 0.998, "bus2.1": 0.98, "bus3.3": 0.92}
    res_path = plot_feeder_voltage_heatmap(
        minimal_dss_circuit, evaluations, "bus1", load_spec, bounds, voltages, out_png
    )
    assert res_path.exists()
    assert res_path.stat().st_size > 0


def test_plot_voltage_profiles(tmp_path: Path):
    """Test generating before/after voltage profile comparison plot."""
    out_png = tmp_path / "test_voltage_profile.png"
    base_v = {"1.1": 1.0, "1.2": 1.0, "1.3": 1.0, "2.1": 0.99, "2.2": 0.99, "2.3": 0.99}
    final_v = {"1.1": 0.995, "1.2": 0.995, "1.3": 0.995, "2.1": 0.97, "2.2": 0.97, "2.3": 0.97}
    bounds = VoltageBounds(v_min=0.95, v_max=1.05)
    res_path = plot_voltage_profiles(base_v, final_v, bounds, "2", out_png)
    assert res_path.exists()
    assert res_path.stat().st_size > 0
