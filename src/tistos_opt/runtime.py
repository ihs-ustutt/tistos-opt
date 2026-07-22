"""Runtime bridge to the supplied TiStoS CFD implementation.

The external dtOO and OpenFOAM runtime is imported only inside an evaluation
worker. This keeps case discovery and configuration checks lightweight.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import zlib
from contextlib import contextmanager
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterator

from tistos_opt.case import PARAMETERS


def evaluate(request: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Evaluate one candidate with the supplied TiStoS implementation."""

    scratch_dir = Path(request["context"]["scratch_dir"]).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    resources = request["context"]["resources"]
    mpi_ranks = int(resources["mpi_ranks"])
    if mpi_ranks < 1:
        raise ValueError("mpi_ranks must be at least one")

    os.environ["TMPDIR"] = str(scratch_dir)
    os.environ["FLOW_OPT_MPI_RANKS"] = str(mpi_ranks)
    work_dir = _stage_case(scratch_dir)
    parameters = request["candidate"]["parameters"]
    vector = [float(parameters[item.name]) for item in PARAMETERS]
    candidate_id = str(request["candidate"]["id"])
    state = _state_label(candidate_id)

    with _working_directory(work_dir):
        module = _load_implementation(work_dir)
        fitness, extra, legacy_state, history = module.runTistos(vector, state)

    return float(fitness), {
        "state": legacy_state,
        "fitness_components": _json_compatible(extra),
        "history": _json_compatible(history),
    }


def _stage_case(scratch_dir: Path) -> Path:
    """Copy immutable package resources into a candidate-local work tree."""

    work_dir = scratch_dir / "tistos"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    package_root = _package_root()
    legacy_root = package_root / "_legacy"
    data_root = package_root / "_case_data"
    shutil.copy2(legacy_root / "sim_tistos.py", work_dir / "sim_tistos.py")
    _copy_tree(legacy_root / "tistos_files", work_dir / "tistos_files")
    _copy_tree(data_root / "xml", work_dir / "xml")
    _copy_tree(
        data_root / "boundaryData_RU_INLET",
        work_dir / "boundaryData_RU_INLET",
    )
    return work_dir


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"TiStoS package resource is missing: {source}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _load_implementation(work_dir: Path) -> Any:
    source = work_dir / "sim_tistos.py"
    sys.path.insert(0, str(work_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "tistos_implementation", source
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"cannot load TiStoS implementation from {source}"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(work_dir))


def _package_root() -> Path:
    root = files("tistos_opt")
    if not isinstance(root, Path):
        raise RuntimeError("tistos-opt requires an unpacked installation")
    return root


def _implementation_path() -> Path:
    """Return the bundled legacy entry point for diagnostics."""

    return _package_root() / "_legacy" / "sim_tistos.py"


def _state_label(candidate_id: str) -> str:
    """Create the numeric-suffix state label required by legacy TiStoS."""

    number = zlib.crc32(candidate_id.encode("utf-8"))
    return f"TISTOS_{number}"


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _json_compatible(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        return _json_compatible(item())
    return value


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)
