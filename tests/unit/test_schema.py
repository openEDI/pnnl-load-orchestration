"""Test schema and component_definition synchronization."""

import json
from pathlib import Path

from pnnl_load_orchestration.schemas import ComponentParameters


def test_schema_and_component_definition() -> None:
    """Verify schema.json matches ComponentParameters and static_inputs in component_definition.json align."""
    repo_root = Path(__file__).resolve().parents[2]

    # 1. Regenerate and verify schema.json matches ComponentParameters
    schema_path = repo_root / "schema.json"
    model_schema = ComponentParameters.model_json_schema()
    with open(schema_path, encoding="utf-8") as f:
        existing_schema = json.load(f)
    assert model_schema == existing_schema, "schema.json is out of sync with ComponentParameters model."

    # 2. Verify component_definition.json static_inputs match ComponentParameters properties
    comp_def_path = repo_root / "component_definition.json"
    with open(comp_def_path, encoding="utf-8") as f:
        comp_def = json.load(f)

    static_inputs = comp_def.get("static_inputs", [])
    static_input_names = {item["port_id"] for item in static_inputs}
    schema_properties = set(model_schema.get("properties", {}).keys()) - {"name"}

    missing = schema_properties - static_input_names
    extra = static_input_names - schema_properties

    assert static_input_names == schema_properties, (
        "Mismatch between component_definition.json static_inputs and ComponentParameters schema properties.\n"
        f"Missing in component_definition.json: {missing}\n"
        f"Extra in component_definition.json: {extra}"
    )
