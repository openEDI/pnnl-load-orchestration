"""Unit tests for configuration and schema validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pnnl_load_orchestration.schemas import (
    BusEvaluationResult,
    LoadSpec,
    OrchestrationConfig,
    OrchestrationSummary,
    VoltageBounds,
)


def test_load_spec_valid():
    """Test creating valid LoadSpec instances."""
    spec = LoadSpec(kw_total=1700.0, kvar_total=100.0, kv_base=2.4)
    assert spec.kw_total == 1700.0
    assert spec.kvar_total == 100.0
    assert spec.kv_base == 2.4
    assert spec.conn == "Wye"
    assert spec.model_type == 1
    assert spec.load_name_prefix == "DC"


def test_load_spec_invalid_kw():
    """Test that non-positive kW raises ValidationError."""
    with pytest.raises(ValidationError):
        LoadSpec(kw_total=0)
    with pytest.raises(ValidationError):
        LoadSpec(kw_total=-50)


def test_voltage_bounds_valid():
    """Test valid voltage bounds."""
    bounds = VoltageBounds(v_min=0.95, v_max=1.05)
    assert bounds.v_min == 0.95
    assert bounds.v_max == 1.05


def test_voltage_bounds_invalid():
    """Test that v_min >= v_max raises ValidationError."""
    with pytest.raises(ValidationError):
        VoltageBounds(v_min=1.05, v_max=0.95)
    with pytest.raises(ValidationError):
        VoltageBounds(v_min=1.0, v_max=1.0)


def test_orchestration_config_valid(minimal_dss_circuit: Path, tmp_path: Path):
    """Test creating valid OrchestrationConfig."""
    out_dir = tmp_path / "out"
    config = OrchestrationConfig(
        model_dir=minimal_dss_circuit,
        master_file="master.dss",
        candidate_buses=["bus1", "bus2", "bus3"],
        load_spec=LoadSpec(kw_total=500.0),
        output_dir=out_dir,
    )
    assert config.model_dir == minimal_dss_circuit.resolve()
    assert config.candidate_buses == ["bus1", "bus2", "bus3"]
    assert config.output_dir == out_dir.resolve()
    assert config.in_place is False


def test_orchestration_config_in_place_conflict(minimal_dss_circuit: Path, tmp_path: Path):
    """Test error when specifying both in_place=True and output_dir."""
    with pytest.raises(ValidationError, match="Cannot specify both in_place=True and output_dir"):
        OrchestrationConfig(
            model_dir=minimal_dss_circuit,
            master_file="master.dss",
            candidate_buses=["bus1"],
            load_spec=LoadSpec(kw_total=500.0),
            output_dir=tmp_path / "out",
            in_place=True,
        )


def test_orchestration_config_missing_model_dir(tmp_path: Path):
    """Test error when model_dir does not exist."""
    with pytest.raises(ValidationError, match="model_dir does not exist"):
        OrchestrationConfig(
            model_dir=tmp_path / "non_existent_dir",
            master_file="master.dss",
            candidate_buses=["bus1"],
            load_spec=LoadSpec(kw_total=500.0),
        )


def test_orchestration_config_missing_master(tmp_path: Path):
    """Test error when master file is not found in model_dir."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    with pytest.raises(ValidationError, match="Master file .* not found"):
        OrchestrationConfig(
            model_dir=empty_dir,
            master_file="master.dss",
            candidate_buses=["bus1"],
            load_spec=LoadSpec(kw_total=500.0),
        )


def test_orchestration_summary_serialization():
    """Test serialization and deserialization of OrchestrationSummary."""
    eval_res = BusEvaluationResult(
        bus_id="bus1",
        phases=[1, 2, 3],
        violation=False,
        min_voltage=0.98,
        max_voltage=1.02,
        violating_nodes=[],
    )
    summary = OrchestrationSummary(
        success=True,
        allocated_bus="bus1",
        load_spec=LoadSpec(kw_total=500.0),
        evaluations=[eval_res],
        output_directory="/tmp/test",
        generated_files=["/tmp/test/extra_loads.dss"],
    )
    json_str = summary.model_dump_json()
    loaded = OrchestrationSummary.model_validate_json(json_str)
    assert loaded.success is True
    assert loaded.allocated_bus == "bus1"
    assert len(loaded.evaluations) == 1
    assert loaded.evaluations[0].min_voltage == 0.98
