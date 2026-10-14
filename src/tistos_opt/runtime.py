"""Implementation of the explicit TiStoS evaluation stages.

Geometry runs in child processes; postprocessing is imported only in finalize.
Python code comes from the installed package, while each candidate gets its
own mutable case data.

Read the public functions first: prepare -> configure_turbulent -> finalize.
The backend runs simpleFoam between these Python stages (see case.py). The
private helpers configure OpenFOAM and manage case/state files; they are not
part of the hydroflow-opt plugin contract.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from hydroflow_opt.models import EvaluationResult
from hydroflow_opt.results import write_result

from tistos_opt._legacy.sim_tistos import cleanup_case, prepare_case
from tistos_opt.case import _state_label
from tistos_opt.options import SolverOptions


def prepare(request_path: Path, state_path: Path) -> None:
    """Generate and decompose one case, ready for the laminar solve."""
    request = _read_json(request_path)
    options = SolverOptions.from_options(
        request.get("case", {}).get("options", {})
    )
    candidate = request["candidate"]
    candidate_id = str(candidate["id"])
    state = _state_label(candidate_id)
    parameters = candidate["parameters"]
    resources = request["context"]["resources"]
    mpi_ranks = int(resources["mpi_ranks"])
    if mpi_ranks < 1:
        raise ValueError("mpi_ranks must be at least one")

    scratch_dir = Path(request["context"]["scratch_dir"]).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch_dir)
    work_dir = _stage_case(scratch_dir)

    history = prepare_case(work_dir, state, parameters)

    case_dir = work_dir / f"tistos_ru_of_n_{state}"
    _run_case_command(case_dir, ["checkMesh"], "log.checkMesh")
    if mpi_ranks > 1:
        _configure_decomposition(case_dir, mpi_ranks)
        _run_case_command(
            case_dir,
            ["decomposePar", "-fileHandler", "collated"],
            "log.decomposePar",
        )
    _configure_laminar(case_dir, options.laminar_iterations)

    # Later stages start fresh processes: persist paths and history, not dtOO
    # objects. This state file is plugin-owned; request.json is core-owned.
    _write_json(
        state_path,
        {
            "candidate_id": candidate_id,
            "state": state,
            "mpi_ranks": mpi_ranks,
            "solver_options": asdict(options),
            "work_dir": str(work_dir),
            "case_dir": str(case_dir),
            "history": history,
        },
    )


def configure_turbulent(state_path: Path) -> None:
    """Switch a prepared case from laminar to turbulent settings."""
    state = _read_state(state_path)
    options = SolverOptions.from_options(state.get("solver_options", {}))
    _configure_turbulent(Path(state["case_dir"]), options.end_time)


def finalize(
    request_path: Path,
    state_path: Path,
    result_path: Path,
) -> None:
    """Reconstruct, evaluate, persist, and then clean a completed case."""
    request = _read_json(request_path)
    state_data = _read_state(state_path)
    options = SolverOptions.from_options(state_data.get("solver_options", {}))
    candidate_id = str(request["candidate"]["id"])
    if state_data["candidate_id"] != candidate_id:
        raise ValueError("TiStoS state does not match the candidate request")

    work_dir = Path(state_data["work_dir"])
    case_dir = Path(state_data["case_dir"])
    mpi_ranks = int(state_data["mpi_ranks"])
    state = str(state_data["state"])
    # Postprocessing expects a single reconstructed case, even after MPI runs.
    if mpi_ranks > 1:
        _run_case_command(case_dir, ["reconstructPar"], "log.reconstructPar")
        for processor_dir in case_dir.glob("processor*"):
            if processor_dir.is_dir():
                shutil.rmtree(processor_dir)

    # Only this stage needs pyDtOO; import it at the point of use.
    from tistos_opt._legacy.tistos_files.tistosPyBib import evaluate_case

    fitness, extra, history = evaluate_case(
        case_dir, options, state_data.get("history", {})
    )

    result = EvaluationResult.success(
        candidate_id,
        float(fitness),
        metadata={
            "state": state,
            "solver_options": asdict(options),
            "fitness_components": extra,
            "history": history,
        },
    )
    write_result(result_path, result)

    # Persist the objective and diagnostics before deleting generated files.
    cleanup_case(work_dir, state)


def _configure_decomposition(case_dir: Path, mpi_ranks: int) -> None:
    """Match OpenFOAM's partition count to the plan's solver resources."""
    path = case_dir / "system" / "decomposeParDict"
    _replace_assignment(path, "numberOfSubdomains", str(mpi_ranks))
    _replace_assignment(path, "method", "scotch")


def _configure_laminar(case_dir: Path, end_time: int = 100) -> None:
    """Set the initial solve's stop/write time and laminar discretization."""
    _replace_assignment(
        case_dir / "system" / "controlDict", "endTime", str(end_time)
    )
    _replace_assignment(
        case_dir / "system" / "controlDict", "writeInterval", str(end_time)
    )
    _replace_assignment(
        case_dir / "constant" / "turbulenceProperties",
        "turbulence",
        "off",
    )
    _replace_text(case_dir / "system" / "fvSchemes", "cellL", "faceL")


def _configure_turbulent(case_dir: Path, end_time: int = 500) -> None:
    """Set the second solve's stop/write time and turbulent discretization."""
    _replace_assignment(
        case_dir / "system" / "controlDict", "endTime", str(end_time)
    )
    _replace_assignment(
        case_dir / "system" / "controlDict", "writeInterval", str(end_time)
    )
    _replace_assignment(
        case_dir / "constant" / "turbulenceProperties",
        "turbulence",
        "on",
    )
    _replace_text(case_dir / "system" / "fvSchemes", "faceL", "cellL")


def _replace_assignment(path: Path, name: str, value: str) -> None:
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*{re.escape(name)}\s+)[^;]+;", re.MULTILINE)
    updated, count = pattern.subn(rf"\g<1>{value};", content)
    if count == 0:
        raise RuntimeError(f"cannot find '{name}' assignment in {path}")
    path.write_text(updated, encoding="utf-8")


def _replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        raise RuntimeError(f"cannot find '{old}' in {path}")
    path.write_text(content.replace(old, new), encoding="utf-8")


def _run_case_command(
    case_dir: Path, command: list[str], log_name: str
) -> None:
    """Run a serial utility; the backend launches the solver stages."""
    with (case_dir / log_name).open("w", encoding="utf-8") as log:
        subprocess.run(
            command,
            check=True,
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )


def _stage_case(scratch_dir: Path) -> Path:
    """Copy case data into a candidate-local work tree."""
    work_dir = scratch_dir / "tistos"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    package_root = _package_root()
    legacy_root = package_root / "_legacy"
    data_root = package_root / "_case_data"
    template_dir = work_dir / "tistos_files"
    template_dir.mkdir()
    for name in ("machine.xml", "templateState.xml"):
        shutil.copy2(legacy_root / "tistos_files" / name, template_dir / name)
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


def _package_root() -> Path:
    root = files("tistos_opt")
    if not isinstance(root, Path):
        raise RuntimeError("tistos-opt requires an unpacked installation")
    return root


def _implementation_path() -> Path:
    """Return the bundled legacy entry point for diagnostics."""
    return _package_root() / "_legacy" / "sim_tistos.py"


def _read_state(path: Path) -> dict[str, Any]:
    """Check the minimum handoff data needed by subsequent stages."""
    state = _read_json(path)
    required = {
        "candidate_id",
        "state",
        "mpi_ranks",
        "work_dir",
        "case_dir",
    }
    missing = required.difference(state)
    if missing:
        raise ValueError(
            "TiStoS state is missing: " + ", ".join(sorted(missing))
        )
    return state


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    """Publish complete state so a later stage cannot read a partial write."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
