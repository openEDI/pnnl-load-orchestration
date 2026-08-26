"""Command-line interface for pnnl-load-orchestration."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .allocator import LoadAllocator
from .schemas import OrchestrationConfig

logger = logging.getLogger("pnnl_load_orchestration")


def generate_template_config(target_path: Path) -> None:
    """Generate a starter JSON configuration template.

    Args:
        target_path: Destination path for sample configuration JSON.
    """
    sample = {
        "model_dir": "/path/to/opendss/model",
        "master_file": "master.dss",
        "candidate_buses": ["83", "65", "47", "48", "76"],
        "load_spec": {
            "kw_total": 1700.0,
            "kvar_total": 0.0,
            "kv_base": 2.4,
            "conn": "Wye",
            "model_type": 1,
            "load_name_prefix": "DC",
        },
        "bounds": {
            "v_min": 0.95,
            "v_max": 1.05,
        },
        "output_dir": "./output/orchestrated_model",
        "in_place": False,
        "strategy": "first_feasible",
    }
    target_path = target_path.resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)
    print(f"Generated sample configuration template at: {target_path}")


def main(argv: list[str] | None = None) -> int:
    """Main CLI entrypoint.

    Args:
        argv: Optional command-line arguments list.

    Returns:
        Exit code (0 on success, non-zero on failure).
    """
    parser = argparse.ArgumentParser(
        prog="pnnl-load-orchestration",
        description="Preprocessing component for large load orchestration in constrained power distribution networks.",
    )
    parser.add_argument(
        "config_file",
        nargs="?",
        type=Path,
        help="Path to JSON configuration file.",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_opt",
        type=Path,
        help="Path to JSON configuration file (alternative to positional argument).",
    )
    parser.add_argument(
        "--init-config",
        type=Path,
        metavar="PATH",
        help="Generate a starter configuration template JSON file at PATH.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level (default: INFO).",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.init_config:
        generate_template_config(args.init_config)
        return 0

    config_path = args.config_file or args.config_opt
    if not config_path:
        parser.print_help()
        print("\nError: Please provide a configuration file path or run with --init-config <path>.")
        return 1

    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        return 1

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)

        config = OrchestrationConfig.model_validate(config_data)
        logger.info("Loaded configuration from: %s", config_path.resolve())

        allocator = LoadAllocator(config)
        summary = allocator.run()

        print("\n==================================================")
        print("           LOAD ORCHESTRATION SUMMARY             ")
        print("==================================================")
        print(f"Status:             {'SUCCESS' if summary.success else 'FAILED'}")
        print(f"Allocated Bus:      {summary.allocated_bus or 'None'}")
        print(f"Load Total (kW):    {summary.load_spec.kw_total} kW")
        print(f"Output Directory:   {summary.output_directory}")
        print("Evaluations:")
        for ev in summary.evaluations:
            status_str = "VIOLATION" if ev.violation else "PASSED"
            print(
                f"  Bus {ev.bus_id:>4} (phases {ev.phases}): {status_str:<9} "
                f"min: {ev.min_voltage:.4f} p.u., max: {ev.max_voltage:.4f} p.u."
            )
        print("==================================================\n")

        return 0 if summary.success else 2

    except Exception as exc:
        logger.exception("Load orchestration failed with error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
