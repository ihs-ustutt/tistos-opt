"""Runtime environment checks for the TiStoS case plugin."""

from dataclasses import dataclass
from importlib import import_module
from shutil import which

from tistos_opt.runtime import _implementation_path, _package_root


@dataclass(frozen=True)
class CheckResult:
    """Result of one runtime readiness check."""

    name: str
    passed: bool
    detail: str = ""
    required: bool = True


def run_checks() -> list[CheckResult]:
    """Run package, dtOO, OpenFOAM, and MPI readiness checks."""
    return [
        _check_import("dtOOPythonSWIG"),
        _check_import("pyDtOO"),
        _check_import("hydroflow_opt"),
        _check_import("tistos_opt"),
        _check_executable("simpleFoam"),
        _check_executable("checkMesh"),
        _check_executable("mpiexec", required=False),
        _check_executable("decomposePar", required=False),
        _check_executable("reconstructPar", required=False),
        _check_implementation(),
        _check_case_data(),
    ]


def failed_required_count(results: list[CheckResult]) -> int:
    """Count required checks that failed."""
    return sum(
        1 for result in results if result.required and not result.passed
    )


def format_report(
    results: list[CheckResult],
    *,
    environ: dict[str, str],
) -> str:
    """Format runtime check results for terminal output."""
    lines = ["tistos-opt runtime check", ""]
    for result in results:
        if result.passed:
            status = "OK  "
        elif result.required:
            status = "FAIL"
        else:
            status = "WARN"
        detail = f": {result.detail}" if result.detail else ""
        lines.append(f"{status} {result.name}{detail}")

    lines.extend(
        [
            "",
            "Environment",
            _format_env("TMPDIR", environ, default="<not set>"),
            _format_env("PYTHONPATH", environ, default="<not set>"),
            _format_env("LD_LIBRARY_PATH", environ, default="<not set>"),
            "",
        ]
    )
    failed = failed_required_count(results)
    if failed:
        lines.append(
            f"Runtime check failed: {failed} required check(s) failed."
        )
    else:
        lines.append("Runtime check passed.")
    return "\n".join(lines)


def _check_import(module_name: str) -> CheckResult:
    try:
        import_module(module_name)
    except Exception as exc:
        return CheckResult(
            name=f"import {module_name}",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return CheckResult(name=f"import {module_name}", passed=True)


def _check_executable(name: str, *, required: bool = True) -> CheckResult:
    path = which(name)
    if path is None:
        return CheckResult(
            name=f"executable {name}",
            passed=False,
            detail="not found on PATH",
            required=required,
        )
    return CheckResult(
        name=f"executable {name}",
        passed=True,
        detail=path,
        required=required,
    )


def _check_implementation() -> CheckResult:
    path = _implementation_path()
    if not path.is_file():
        return CheckResult(
            name="sim_tistos.py",
            passed=False,
            detail=f"not found at {path}",
        )
    return CheckResult(name="sim_tistos.py", passed=True, detail=str(path))


def _check_case_data() -> CheckResult:
    package_root = _package_root()
    required_paths = (
        package_root / "_legacy" / "tistos_files" / "machine.xml",
        package_root / "_legacy" / "tistos_files" / "templateState.xml",
        package_root / "_case_data" / "xml" / "tistos_ru_of.xml",
        package_root
        / "_case_data"
        / "boundaryData_RU_INLET"
        / "n"
        / "boundaryData"
        / "RU_INLET"
        / "0"
        / "U",
    )
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        return CheckResult(
            name="bundled case data",
            passed=False,
            detail="missing: " + ", ".join(missing),
        )
    return CheckResult(
        name="bundled case data",
        passed=True,
        detail=str(package_root / "_case_data"),
    )


def _format_env(
    name: str,
    environ: dict[str, str],
    *,
    default: str,
) -> str:
    return f"  {name}={environ.get(name, default)}"
