# pnnl-load-orchestration

Preprocessing component for large load orchestration (e.g. data centers, EV fleet hubs) in constrained power distribution networks.

This tool evaluates candidate bus locations on an OpenDSS network model, evaluates power flow and nodal voltage constraints against specified voltage bounds (ANSI C84.1), and generates an updated OpenDSS circuit model along with visualizations (distribution feeder line voltage heatmap and voltage profile comparison).

---

## Features

- **OEDISI Component Aligned**: Standard `component_definition.json` and auto-generated `schema.json` from `ComponentParameters`.
- **No Runtime Federate Overhead**: Designed as an offline/preprocessing component without HELICS or FastAPI server loops.
- **Config & Scenario Driven**: Single JSON configuration input under `scenarios/` specifying model paths, candidate buses, load specs, bounds, and outputs.
- **Dynamic Phase Discovery**: Discovers connected phases on candidate buses directly from the compiled OpenDSS circuit (with optional manual override).
- **Rich Visualizations**:
  - `feeder_voltage_heatmap.png`: Feeder network topology with distribution lines and buses heatmapped by per-unit voltage magnitude, overlaid with candidate bus compliance tags and the selected load placement.
  - `voltage_profile_comparison.png`: Feeder-wide nodal voltage profile comparing the base circuit against the orchestrated circuit with ANSI C84.1 limit lines.
- **Structured Outputs**: Model DSS files, `orchestration_summary.json`, and figures saved to `outputs/<scenario_name>/`.

---

## Installation

This repository is managed with [`uv`](https://docs.astral.sh/uv/):

```bash
# Clone the repository
git clone https://github.com/openEDI/pnnl-load-orchestration.git
cd pnnl-load-orchestration

# Sync environment with all dependencies including dev tools
uv sync --all-extras
```

---

## Quick Start

### 1. View or Edit a Scenario Configuration

Example scenario in `scenarios/ieee123_datacenter.json`:

```json
{
  "name": "ieee123_datacenter_orchestration",
  "model_dir": "/path/to/Powergrid-Models/models/feeders/OpenDSS/IEEE/IEEE123",
  "master_file": "IEEE123Master.dss",
  "candidate_buses": ["83", "65", "47", "48", "76"],
  "load_spec": {
    "kw_total": 1700.0,
    "kvar_total": 0.0,
    "kv_base": 2.4,
    "conn": "Wye",
    "model_type": 1,
    "load_name_prefix": "DC"
  },
  "bounds": {
    "v_min": 0.95,
    "v_max": 1.05
  },
  "output_dir": "outputs/ieee123_datacenter",
  "in_place": false,
  "strategy": "first_feasible",
  "plot_results": true
}
```

### 2. Run Load Orchestration

```bash
uv run pnnl-load-orchestration scenarios/ieee123_datacenter.json
```

Outputs will be saved in `outputs/ieee123_datacenter/`:
- `IEEE123Master.dss` (updated with `Redirect orchestrated_load_76.dss`)
- `orchestrated_load_76.dss` (new load definitions)
- `orchestration_summary.json` (machine-readable run summary)
- `feeder_voltage_heatmap.png` (distribution network line voltage heatmap)
- `voltage_profile_comparison.png` (before/after nodal voltage profiles)

---

## Development & Testing

### Running Tests

```bash
# Run all unit and integration tests
uv run pytest -v

# Run schema and component definition verification
uv run pytest tests/unit/test_schema.py -v

# Run plotting tests
uv run pytest tests/unit/test_plotting.py -v
```

### Code Quality & Pre-commit

```bash
# Run linter and formatter checks
uv run ruff check .
uv run ruff format --check .

# Run type checker
uv run mypy src

# Run pre-commit hooks
uv run pre-commit run --all-files
```

---

## License

MIT License.
