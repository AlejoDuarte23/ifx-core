import argparse
import json
import math
import sys
from pathlib import Path

from .manifest import inventory, load_manifest
from .runner import build, run_suite, worker, write_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strict local IFC compatibility checks. No uploads or CI."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "build", help="build the native core and record its source and binary hashes"
    )
    discover = commands.add_parser("inventory", help="make a deduplicated private model manifest")
    discover.add_argument("directory", type=Path)
    discover.add_argument("--schema", default="IFC2X3")
    discover.add_argument("--output", type=Path, required=True)
    check = commands.add_parser(
        "check", help="check every manifest model and the self-contained fixture matrix"
    )
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--report", type=Path, required=True)
    check.add_argument("--timeout", type=float, default=180)
    check.add_argument("--bounds-m", type=float, default=0.002)
    check.add_argument("--area-relative", type=float, default=0.02)
    check.add_argument("--volume-relative", type=float, default=0.02)
    child = commands.add_parser("worker", help=argparse.SUPPRESS)
    child.add_argument("job", type=Path)
    child.add_argument("result", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.command == "build":
            build()
        elif arguments.command == "inventory":
            if arguments.output.suffix.lower() != ".json":
                raise ValueError("manifest output must use the .json extension")
            result = inventory(arguments.directory, arguments.schema.strip().upper())
            write_json(arguments.output, result)
            print(f"{len(result['models'])} unique models; {result['duplicates']} duplicates")
        elif arguments.command == "worker":
            worker(json.loads(arguments.job.read_text()), arguments.result)
        else:
            from .mesh import Tolerances

            if not math.isfinite(arguments.timeout) or arguments.timeout <= 0:
                raise ValueError("timeout must be positive and finite")
            if arguments.manifest.resolve() == arguments.report.resolve():
                raise ValueError("report must not overwrite the model manifest")
            if arguments.report.suffix.lower() != ".json":
                raise ValueError("report output must use the .json extension")
            models = load_manifest(arguments.manifest)
            limits = Tolerances(
                arguments.bounds_m, arguments.area_relative, arguments.volume_relative
            )
            result = run_suite(models, arguments.report, arguments.timeout, limits)
            return 0 if result["status"] == "pass" else 1
        return 0
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        print(message, file=sys.stderr)
        if (
            arguments.command == "check"
            and arguments.manifest.resolve() != arguments.report.resolve()
            and arguments.report.suffix.lower() == ".json"
        ):
            write_json(
                arguments.report,
                {"version": 1, "status": "fail", "preflight_error": message, "cases": []},
            )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
