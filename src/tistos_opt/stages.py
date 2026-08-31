"""Command-line entry points for individual TiStoS evaluation stages."""

import argparse
from pathlib import Path

from tistos_opt.runtime import configure_turbulent, finalize, prepare


def main(argv: list[str] | None = None) -> int:
    """Run one stage selected by the hydroflow-opt evaluation plan."""

    parser = argparse.ArgumentParser(prog="python -m tistos_opt.stages")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("request", type=Path)
    prepare_parser.add_argument("state", type=Path)

    turbulent_parser = subparsers.add_parser("configure-turbulent")
    turbulent_parser.add_argument("state", type=Path)

    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("request", type=Path)
    finalize_parser.add_argument("state", type=Path)
    finalize_parser.add_argument("result", type=Path)

    args = parser.parse_args(argv)
    if args.stage == "prepare":
        prepare(args.request, args.state)
    elif args.stage == "configure-turbulent":
        configure_turbulent(args.state)
    elif args.stage == "finalize":
        finalize(args.request, args.state, args.result)
    else:
        parser.error(f"unknown stage: {args.stage}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
