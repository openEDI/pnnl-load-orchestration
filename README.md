# pnnl-load-orchestration

Preprocessing component for large load orchestration (e.g. data centers, EV fleet hubs) in constrained power distribution networks.

This tool evaluates candidate bus locations on an OpenDSS network model, evaluates power flow and nodal voltage constraints against specified voltage bounds (ANSI C84.1), and generates an updated OpenDSS circuit model with the allocated load.

---

## Features

- **No Runtime Federate Overhead**: Designed as an offline/preprocessing component aligned with OEDISI component structures without the HELICS or FastAPI server loop.
- **Config-File Driven**: Single JSON configuration input specifying model paths, candidate buses, load requirements, voltage bounds, and output options.
- **Dynamic Phase Discovery**: Automatically discovers connected phases on candidate buses directly from the compiled OpenDSS circuit (with optional manual override).
- **Automated OpenDSS Model Generation**: Generates dedicated load definition DSS files and updates `master.dss` in the destination directory or in place.
- **Structured JSON Summaries**: Outputs execution details, minimum/maximum voltage bounds per bus, and violating nodes to `orchestration_summary.json`.

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

### 1. Generate a Template Configuration

```bash
uv run pnnl-load-orchestration --init-config config.json
```

### 2. Configure Your Run

Edit `config.json`:

```json
{
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
  "output_dir": "./output/ieee123_orchestrated",
  "in_place": false,
  "strategy": "first_feasible"
}
```

### 3. Run Load Orchestration

```bash
uv run pnnl-load-orchestration config.json
```

---

## Development & Testing

### Running Tests

```bash
# Run unit and integration tests
uv run pytest -v

# Run only unit tests
uv run pytest tests/unit

# Run integration tests with IEEE 123
uv run pytest tests/integration
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
