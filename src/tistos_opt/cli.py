"""Command-line utilities for the TiStoS case plugin."""

import argparse
import os

from tistos_opt.runtime_check import (
    failed_required_count,
    format_report,
    run_checks,
)


def main(argv: list[str] | None = None) -> int:
    """Run the TiStoS plugin command-line interface."""

    parser = argparse.ArgumentParser(prog="tistos-opt")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check-runtime")
    args = parser.parse_args(argv)

    if args.command == "check-runtime":
        results = run_checks()
        print(format_report(results, environ=dict(os.environ)))
        return 1 if failed_required_count(results) else 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
