"""Unit tests for OpenDSSEngine."""

from pathlib import Path

from pnnl_load_orchestration.dss_engine import OpenDSSEngine
from pnnl_load_orchestration.schemas import LoadSpec, VoltageBounds


def test_dss_engine_compile_and_extract(minimal_dss_circuit: Path):
    """Test compiling a circuit and extracting node voltages."""
    master_path = minimal_dss_circuit / "master.dss"
    engine = OpenDSSEngine(master_path)
    engine.compile()

    converged = engine.solve()
    assert converged is True

    voltages = engine.extract_nodal_voltages()
    assert len(voltages) > 0
    # Source voltages should be near 1.0 p.u.
    assert any("source" in k.lower() or "bus1" in k.lower() for k in voltages)
    for _node, v in voltages.items():
        assert 0.5 < v < 1.5


def test_dss_engine_discover_phases(minimal_dss_circuit: Path):
    """Test phase discovery on 3-phase and 1-phase buses."""
    master_path = minimal_dss_circuit / "master.dss"
    engine = OpenDSSEngine(master_path)
    engine.compile()

    # bus1 is 3-phase
    phases_bus1 = engine.discover_bus_phases("bus1")
    assert phases_bus1 == [1, 2, 3]

    # bus3 is 1-phase (connected to phase 3)
    phases_bus3 = engine.discover_bus_phases("bus3")
    assert phases_bus3 == [3]


def test_dss_engine_check_voltage_violations(minimal_dss_circuit: Path):
    """Test voltage violation checker."""
    master_path = minimal_dss_circuit / "master.dss"
    engine = OpenDSSEngine(master_path)
    engine.compile()

    voltages = {"bus1.1": 1.01, "bus1.2": 0.99, "bus1.3": 1.02}
    bounds = VoltageBounds(v_min=0.95, v_max=1.05)
    has_viol, min_v, max_v, bad_nodes = engine.check_voltage_violations(voltages, bounds)
    assert has_viol is False
    assert min_v == 0.99
    assert max_v == 1.02
    assert len(bad_nodes) == 0

    # Test violation
    voltages_bad = {"bus1.1": 0.92, "bus1.2": 0.99, "bus1.3": 1.06}
    has_viol, min_v, max_v, bad_nodes = engine.check_voltage_violations(voltages_bad, bounds)
    assert has_viol is True
    assert min_v == 0.92
    assert max_v == 1.06
    assert set(bad_nodes) == {"bus1.1", "bus1.3"}


def test_dss_engine_add_and_remove_load(minimal_dss_circuit: Path):
    """Test dynamically adding and removing loads."""
    master_path = minimal_dss_circuit / "master.dss"
    engine = OpenDSSEngine(master_path)
    engine.compile()

    load_spec = LoadSpec(kw_total=600.0, kvar_total=100.0, kv_base=2.4)
    created = engine.add_load("bus1", [1, 2, 3], load_spec)
    assert len(created) == 3
    assert created == ["DC_bus1_ph1", "DC_bus1_ph2", "DC_bus1_ph3"]

    engine.solve()
    voltages_with_load = engine.extract_nodal_voltages()

    # Now remove load
    engine.remove_load(created)
    engine.solve()
    voltages_after_removal = engine.extract_nodal_voltages()

    # Removing load should restore higher voltages at bus1
    assert voltages_after_removal["bus1.1"] >= voltages_with_load["bus1.1"]
