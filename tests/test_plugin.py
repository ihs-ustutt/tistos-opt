import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import tistos_opt.runtime as runtime
import tistos_opt.runtime_check as runtime_check
from tistos_opt.case import PARAMETERS, TistosCase
from tistos_opt.cli import main as cli_main
from tistos_opt.runtime_check import CheckResult
from tistos_opt.worker import main as worker_main


def test_case_exposes_all_legacy_parameters_in_order():
    case = TistosCase()
    space = case.parameter_space({})

    assert len(space.names) == 30
    assert space.names == tuple(parameter.name for parameter in PARAMETERS)
    assert space.lower_bounds[:3] == (-0.155, -0.19, -0.19)
    assert space.upper_bounds[-3:] == (0.6, 0.6, 0.6)
    assert case.worker_placement() == "controller"


def test_parameter_labels_exist_in_the_state_template():
    template = (
        runtime._package_root()
        / "_legacy"
        / "tistos_files"
        / "templateState.xml"
    )
    labels = {
        element.attrib["label"]
        for element in ET.parse(template).iter("constValue")
    }

    assert all(parameter.legacy_label in labels for parameter in PARAMETERS)


def test_runtime_maps_parameters_and_resources_without_cfd(
    monkeypatch, tmp_path
):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    observed = {}

    class FakeImplementation:
        @staticmethod
        def runTistos(vector, state, *, solver_launcher, cleanup):
            observed["vector"] = vector
            observed["state"] = state
            observed["solver_launcher"] = solver_launcher
            observed["cleanup"] = cleanup
            return 1.25, {"component": 2.5}, state, {"status": "done"}

        @staticmethod
        def cleanupTistos(state):
            observed["cleaned_state"] = state

    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(
        runtime,
        "_load_implementation",
        lambda staged_work_dir: FakeImplementation,
    )
    values = {
        parameter.name: (parameter.lower_bound + parameter.upper_bound) / 2
        for parameter in PARAMETERS
    }
    request = {
        "candidate": {"id": "island-000-initial-003", "parameters": values},
        "context": {
            "scratch_dir": str(tmp_path / "scratch"),
            "resources": {"mpi_ranks": 4},
            "execution": {
                "backend": "slurm",
                "mpi_launcher": [
                    "srun",
                    "--exclusive",
                    "--ntasks=4",
                ],
            },
        },
    }

    objective, metadata = runtime.evaluate(request)

    assert objective == 1.25
    assert observed["vector"] == [values[item.name] for item in PARAMETERS]
    assert re.fullmatch(r"TISTOS_\d+", observed["state"])
    assert observed["solver_launcher"] == [
        "srun",
        "--exclusive",
        "--ntasks=4",
    ]
    assert observed["cleanup"] is False
    assert observed["cleaned_state"] == observed["state"]
    assert metadata["state"] == observed["state"]
    assert metadata["fitness_components"] == {"component": 2.5}


def test_evaluation_session_exposes_files_until_successful_exit(
    monkeypatch, tmp_path
):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    observed = {}

    class FakeImplementation:
        @staticmethod
        def runTistos(vector, state, *, solver_launcher, cleanup):
            del vector, solver_launcher
            assert cleanup is False
            (work_dir / f"tistos_ru_of_n_{state}").mkdir()
            (work_dir / f"{state}_ru_gridGmsh.msh").touch()
            return 0.5, {}, state, {}

        @staticmethod
        def cleanupTistos(state):
            observed["case_existed_at_cleanup"] = (
                work_dir / f"tistos_ru_of_n_{state}"
            ).is_dir()
            observed["cleaned_state"] = state

    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(
        runtime,
        "_load_implementation",
        lambda staged_work_dir: FakeImplementation,
    )
    request = _runtime_request(tmp_path)

    with runtime.evaluation_session(request) as result:
        assert result.case_dirs["n"].is_dir()
        assert result.mesh_path.is_file()
        assert "cleaned_state" not in observed

    assert observed["case_existed_at_cleanup"] is True
    assert observed["cleaned_state"] == result.state


def test_evaluation_session_preserves_files_when_consumer_fails(
    monkeypatch, tmp_path
):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    observed = {}

    class FakeImplementation:
        @staticmethod
        def runTistos(vector, state, *, solver_launcher, cleanup):
            del vector, solver_launcher, cleanup
            (work_dir / f"tistos_ru_of_n_{state}").mkdir()
            return 0.5, {}, state, {}

        @staticmethod
        def cleanupTistos(state):
            observed["cleaned_state"] = state

    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(
        runtime,
        "_load_implementation",
        lambda staged_work_dir: FakeImplementation,
    )
    request = _runtime_request(tmp_path)

    with pytest.raises(RuntimeError, match="tensor extraction failed"):
        with runtime.evaluation_session(request) as result:
            raise RuntimeError("tensor extraction failed")

    assert result.case_dirs["n"].is_dir()
    assert "cleaned_state" not in observed


def test_evaluation_session_preserves_files_when_cfd_fails(
    monkeypatch, tmp_path
):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    observed = {}

    class FakeImplementation:
        @staticmethod
        def runTistos(vector, state, *, solver_launcher, cleanup):
            del vector, solver_launcher, cleanup
            (work_dir / f"tistos_ru_of_n_{state}").mkdir()
            raise RuntimeError("CFD failed")

        @staticmethod
        def cleanupTistos(state):
            observed["cleaned_state"] = state

    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(
        runtime,
        "_load_implementation",
        lambda staged_work_dir: FakeImplementation,
    )
    request = _runtime_request(tmp_path)

    with pytest.raises(RuntimeError, match="CFD failed"):
        with runtime.evaluation_session(request):
            pass

    assert list(work_dir.glob("tistos_ru_of_n_*"))
    assert "cleaned_state" not in observed


def _runtime_request(tmp_path):
    values = {
        parameter.name: (parameter.lower_bound + parameter.upper_bound) / 2
        for parameter in PARAMETERS
    }
    return {
        "candidate": {"id": "session-test", "parameters": values},
        "context": {
            "scratch_dir": str(tmp_path / "scratch"),
            "resources": {"mpi_ranks": 1},
        },
    }


def test_runtime_defaults_old_requests_to_local_mpiexec(tmp_path):
    request = {
        "context": {
            "scratch_dir": str(tmp_path),
            "resources": {"mpi_ranks": 2},
        }
    }

    assert runtime._solver_launcher(request, 2) == ["mpiexec", "-n", "2"]


def test_runtime_rejects_invalid_backend_solver_launcher(tmp_path):
    request = {
        "context": {
            "scratch_dir": str(tmp_path),
            "resources": {"mpi_ranks": 2},
            "execution": {"backend": "slurm", "mpi_launcher": "srun"},
        }
    }

    with pytest.raises(TypeError, match="must be a string list"):
        runtime._solver_launcher(request, 2)


def test_stage_case_copies_runtime_assets(tmp_path):
    work_dir = runtime._stage_case(tmp_path)

    assert (work_dir / "sim_tistos.py").is_file()
    assert (work_dir / "tistos_files" / "machine.xml").is_file()
    assert (work_dir / "xml" / "tistos_ru_of.xml").is_file()
    assert (
        work_dir
        / "boundaryData_RU_INLET"
        / "n"
        / "boundaryData"
        / "RU_INLET"
        / "0"
        / "U"
    ).is_file()
    assert not list(work_dir.rglob("*.pyc"))


def test_legacy_shell_uses_injected_solver_launcher(tmp_path):
    case_dir = tmp_path / "case"
    system_dir = case_dir / "system"
    constant_dir = case_dir / "constant"
    system_dir.mkdir(parents=True)
    constant_dir.mkdir()
    (system_dir / "controlDict").write_text(
        "writeInterval 1;\nendTime 1;\n", encoding="utf-8"
    )
    (system_dir / "fvSchemes").write_text("cellL\n", encoding="utf-8")
    (system_dir / "decomposeParDict").write_text(
        "numberOfSubdomains 1;\nmethod simple;\n", encoding="utf-8"
    )
    (constant_dir / "turbulenceProperties").write_text(
        "turbulence on;\n", encoding="utf-8"
    )

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    no_op = "#!/bin/sh\nexit 0\n"
    for name in ("checkMesh", "decomposePar", "reconstructPar"):
        executable = bin_dir / name
        executable.write_text(no_op, encoding="utf-8")
        executable.chmod(0o755)

    calls_path = tmp_path / "solver-calls"
    launcher = bin_dir / "backend-launcher"
    launcher.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$SOLVER_CALLS"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
    environment["SOLVER_CALLS"] = str(calls_path)
    script = (
        runtime._package_root()
        / "_legacy"
        / "tistos_files"
        / "sbatch.tistos_ru_of.sh"
    )

    subprocess.run(
        [
            "sh",
            "-e",
            str(script),
            str(case_dir),
            "2",
            str(launcher),
            "--from-backend",
        ],
        check=True,
        env=environment,
    )

    assert calls_path.read_text(encoding="utf-8").splitlines() == [
        "--from-backend simpleFoam -parallel -fileHandler collated",
        "--from-backend simpleFoam -parallel -fileHandler collated",
    ]


def test_worker_writes_a_structured_success(monkeypatch, tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request = {
        "candidate": {"id": "test-1", "parameters": {}},
        "context": {"scratch_dir": str(tmp_path / "scratch")},
    }
    request_path.write_text(json.dumps(request), encoding="utf-8")
    monkeypatch.setattr(
        runtime,
        "evaluate",
        lambda request: (0.5, {"state": "TISTOS_1"}),
    )

    assert worker_main([str(request_path), str(result_path)]) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["candidate_id"] == "test-1"
    assert result["status"] == "success"
    assert result["objective"] == 0.5


def test_worker_converts_runtime_exception_to_failure(monkeypatch, tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request = {
        "candidate": {"id": "test-2", "parameters": {}},
        "context": {"scratch_dir": str(tmp_path / "scratch")},
    }
    request_path.write_text(json.dumps(request), encoding="utf-8")

    def fail(request):
        raise RuntimeError("mesh generation failed")

    monkeypatch.setattr(runtime, "evaluate", fail)

    assert worker_main([str(request_path), str(result_path)]) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"] == "mesh generation failed"


def test_runtime_check_distinguishes_required_and_parallel_tools(monkeypatch):
    monkeypatch.setattr(
        runtime_check,
        "import_module",
        lambda name: object(),
    )
    monkeypatch.setattr(
        runtime_check,
        "which",
        lambda name: (
            None if name in {"mpiexec", "decomposePar"} else f"/bin/{name}"
        ),
    )

    results = runtime_check.run_checks()
    report = runtime_check.format_report(results, environ={})

    assert runtime_check.failed_required_count(results) == 0
    assert "WARN executable mpiexec" in report
    assert "Runtime check passed." in report


def test_runtime_cli_returns_nonzero_for_failed_checks(monkeypatch):
    monkeypatch.setattr(
        "tistos_opt.cli.run_checks",
        lambda: [CheckResult("import dtOOPythonSWIG", False)],
    )

    assert cli_main(["check-runtime"]) == 1


def test_runtime_cli_returns_zero_for_successful_checks(monkeypatch):
    monkeypatch.setattr(
        "tistos_opt.cli.run_checks",
        lambda: [CheckResult("import dtOOPythonSWIG", True)],
    )

    assert cli_main(["check-runtime"]) == 0


def test_worker_command_uses_current_python(tmp_path):
    command = TistosCase().worker_command(
        Path(tmp_path / "request.json"),
        Path(tmp_path / "result.json"),
    )

    assert command[1:3] == ["-m", "tistos_opt.worker"]
