"""Pytest fixtures for pnnl-load-orchestration tests."""

from pathlib import Path

import pytest

IEEE123_DIR = Path("/home/tslay/dev/Powergrid-Models/models/feeders/OpenDSS/IEEE/IEEE123")


@pytest.fixture
def ieee123_model_dir() -> Path:
    """Fixture providing path to IEEE 123-bus OpenDSS feeder."""
    if not IEEE123_DIR.exists():
        pytest.skip(f"IEEE 123 feeder model not found at {IEEE123_DIR}")
    return IEEE123_DIR


@pytest.fixture
def minimal_dss_circuit(tmp_path: Path) -> Path:
    """Fixture creating a minimal, self-contained OpenDSS test feeder."""
    model_dir = tmp_path / "minimal_feeder"
    model_dir.mkdir()
    master_file = model_dir / "master.dss"

    dss_content = """Clear
New Circuit.TestCircuit basekv=4.16 Bus1=source pu=1.00 R1=0 X1=0.0001 R0=0 X0=0.0001

New Line.L1 Phases=3 Bus1=source.1.2.3 Bus2=bus1.1.2.3 R1=0.01 X1=0.02 Length=1.0 units=kft
New Line.L2 Phases=3 Bus1=bus1.1.2.3 Bus2=bus2.1.2.3 R1=0.05 X1=0.10 Length=1.0 units=kft
New Line.L3 Phases=1 Bus1=bus1.3 Bus2=bus3.3 R1=0.50 X1=0.50 Length=2.0 units=kft

New Load.Load1 Bus1=bus1.1.2.3 Phases=3 kV=4.16 kW=50 kvar=10 Model=1 Conn=Wye
New Load.Load2 Bus1=bus2.1.2.3 Phases=3 kV=4.16 kW=50 kvar=10 Model=1 Conn=Wye
New Load.Load3 Bus1=bus3.3 Phases=1 kV=2.4 kW=5 kvar=1 Model=1 Conn=Wye

Set VoltageBases = [4.16, 2.4]
CalcVoltageBases
Solve
"""
    master_file.write_text(dss_content, encoding="utf-8")
    return model_dir
