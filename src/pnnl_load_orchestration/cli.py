"""Command-line interface for pnnl-load-orchestration."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .allocator import LoadAllocator
from .schemas import ComponentParameters

logger = logging.getLogger("pnnl_load_orchestration")


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
        help="Path to JSON scenario/configuration file matching schema.json.",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_opt",
        type=Path,
        help="Path to JSON configuration file (alternative to positional argument).",
    )
    parser.add_argument(
        "--generate-schema",
        type=Path,
        metavar="PATH",
        help="Export the JSON Schema definition to the specified PATH and exit.",
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

    if args.generate_schema:
        ComponentParameters.generate_json_schema(args.generate_schema)
        print(f"Generated schema.json at: {args.generate_schema.resolve()}")
        return 0

    config_path = args.config_file or args.config_opt
    if not config_path:
        parser.print_help()
        print("\nError: Please provide a configuration file path or run with --generate-schema <path>.")
        return 1

    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        return 1

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)

        config = ComponentParameters.model_validate(config_data)
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
