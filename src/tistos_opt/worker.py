"""JSON worker protocol for an isolated TiStoS evaluation."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    """Read one hydroflow request and write one structured result."""

    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        raise SystemExit("usage: tistos-opt-worker REQUEST RESULT")
    request_path, result_path = (Path(value) for value in args)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    try:
        from tistos_opt.runtime import evaluate

        objective, metadata = evaluate(request)
        result = _success(request, objective, metadata, started)
    # The worker process is the isolation boundary for CFD runtime failures.
    except Exception as exc:  # noqa: BLE001
        result = _failure(request, str(exc), started)
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return 0


def _success(
    request: dict[str, Any],
    objective: float,
    metadata: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    return {
        "candidate_id": request["candidate"]["id"],
        "status": "success",
        "objective": objective,
        "timings": {"evaluation": time.perf_counter() - started},
        "metadata": metadata,
        "error": None,
    }


def _failure(
    request: dict[str, Any], error: str, started: float
) -> dict[str, Any]:
    return {
        "candidate_id": request["candidate"]["id"],
        "status": "failed",
        "objective": None,
        "timings": {"evaluation": time.perf_counter() - started},
        "metadata": {},
        "error": error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
