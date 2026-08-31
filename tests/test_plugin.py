import json
import xml.etree.ElementTree as ET

import pytest
from hydroflow_opt.models import Candidate, EvaluationPaths, ResourceRequest

import tistos_opt.runtime as runtime
import tistos_opt.runtime_check as runtime_check
from tistos_opt.case import PARAMETERS, TistosCase, _state_label
from tistos_opt.cli import main as cli_main
from tistos_opt.runtime_check import CheckResult


def test_case_exposes_all_legacy_parameters_in_order():
    space = TistosCase().parameter_space({})

    assert len(space.names) == 30
    assert space.names == tuple(parameter.name for parameter in PARAMETERS)
    assert space.lower_bounds[:3] == (-0.155, -0.19, -0.19)
    assert space.upper_bounds[-3:] == (0.6, 0.6, 0.6)


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


def test_case_builds_the_five_stage_parallel_plan(tmp_path):
    candidate = Candidate("candidate-7", _parameter_values())
    paths = EvaluationPaths(
        evaluation_dir=tmp_path / "evaluation",
        scratch_dir=tmp_path / "scratch",
        request_path=tmp_path / "evaluation" / "request.json",
        result_path=tmp_path / "evaluation" / "result.json",
    )
    resources = ResourceRequest(
        available_cpus=6,
        concurrent_evaluations=1,
        mpi_ranks=3,
        threads_per_rank=2,
    )

    stages = TistosCase().evaluation_plan(candidate, paths, resources).stages

    assert [stage.name for stage in stages] == [
        "prepare",
        "solve-laminar",
        "configure-turbulent",
        "solve-turbulent",
        "finalize",
    ]
    assert stages[0].resources.processes == 1
    assert stages[2].resources.processes == 1
    assert stages[4].resources.processes == 1
    for stage in (stages[1], stages[3]):
        assert stage.command == (
            "simpleFoam",
            "-parallel",
            "-fileHandler",
            "collated",
        )
        assert stage.resources.processes == 3
        assert stage.resources.threads_per_process == 2
    state = _state_label(candidate.id)
    assert stages[1].working_directory == (
        paths.scratch_dir / "tistos" / f"tistos_ru_of_n_{state}"
    )


def test_serial_plan_runs_simple_foam_directly(tmp_path):
    candidate = Candidate("serial", _parameter_values())
    paths = EvaluationPaths(
        tmp_path / "evaluation",
        tmp_path / "scratch",
        tmp_path / "request.json",
        tmp_path / "result.json",
    )
    resources = ResourceRequest()

    stages = TistosCase().evaluation_plan(candidate, paths, resources).stages

    assert stages[1].command == ("simpleFoam",)
    assert stages[3].command == ("simpleFoam",)


def test_prepare_maps_parameters_and_configures_laminar_case(
    monkeypatch, tmp_path
):
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    scratch_dir = tmp_path / "scratch"
    work_dir = scratch_dir / "tistos"
    work_dir.mkdir(parents=True)
    candidate_id = "island-000-initial-003"
    state = _state_label(candidate_id)
    case_dir = work_dir / f"tistos_ru_of_n_{state}"
    _write_case_files(case_dir)
    observed = {}

    class FakeEvaluation:
        MeshOk_ = True

        def __init__(self, vector, state_label):
            observed["vector"] = vector
            observed["state"] = state_label

        def pre(self):
            observed["pre"] = True

        def mesh(self):
            observed["mesh"] = True

        def get_history(self):
            return {"status": "meshed"}

    class FakeImplementation:
        tistos = FakeEvaluation

    commands = []
    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(
        runtime, "_load_implementation", lambda staged: FakeImplementation
    )
    monkeypatch.setattr(
        runtime,
        "_run_case_command",
        lambda case, command, log: commands.append((case, command, log)),
    )
    values = _parameter_values()
    _write_request(request_path, candidate_id, values, scratch_dir, 4)

    runtime.prepare(request_path, state_path)

    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert observed["vector"] == [values[item.name] for item in PARAMETERS]
    assert observed["state"] == state
    assert observed["pre"] is True
    assert observed["mesh"] is True
    assert state_data["candidate_id"] == candidate_id
    assert state_data["history"] == {"status": "meshed"}
    assert commands == [
        (case_dir, ["checkMesh"], "log.checkMesh"),
        (
            case_dir,
            ["decomposePar", "-fileHandler", "collated"],
            "log.decomposePar",
        ),
    ]
    assert "numberOfSubdomains 4;" in _read_decompose(case_dir)
    assert "method scotch;" in _read_decompose(case_dir)
    assert "endTime 100;" in _read_control(case_dir)
    assert "writeInterval 100;" in _read_control(case_dir)
    assert "turbulence off;" in _read_turbulence(case_dir)
    assert "faceL" in _read_schemes(case_dir)


def test_configure_turbulent_updates_openfoam_files(tmp_path):
    case_dir = tmp_path / "case"
    _write_case_files(case_dir)
    runtime._configure_laminar(case_dir)

    runtime._configure_turbulent(case_dir)

    assert "endTime 500;" in _read_control(case_dir)
    assert "writeInterval 500;" in _read_control(case_dir)
    assert "turbulence on;" in _read_turbulence(case_dir)
    assert "cellL" in _read_schemes(case_dir)


def test_finalize_writes_result_before_cleanup(monkeypatch, tmp_path):
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    result_path = tmp_path / "result.json"
    work_dir = tmp_path / "work"
    case_dir = work_dir / "tistos_ru_of_n_TISTOS_1"
    case_dir.mkdir(parents=True)
    (case_dir / "processor0").mkdir()
    _write_request(request_path, "candidate", {}, tmp_path, 2)
    state_path.write_text(
        json.dumps(
            {
                "candidate_id": "candidate",
                "state": "TISTOS_1",
                "vector": [1.0, 2.0],
                "mpi_ranks": 2,
                "work_dir": str(work_dir),
                "case_dir": str(case_dir),
                "history": {"status": "meshed"},
            }
        ),
        encoding="utf-8",
    )
    observed = {}

    class FakeEvaluation:
        def __init__(self, vector, state):
            observed["vector"] = vector
            observed["state"] = state
            self.history_ = {}

        def evaluate(self):
            self.history_["status"] = "evaluated"
            return 0.75, {"eta": 0.9}

        def get_history(self):
            return self.history_

    class FakeImplementation:
        tistos = FakeEvaluation

        @staticmethod
        def cleanupTistos(state):
            observed["result_existed_at_cleanup"] = result_path.is_file()
            observed["cleaned"] = state

    monkeypatch.setattr(
        runtime, "_load_implementation", lambda staged: FakeImplementation
    )
    monkeypatch.setattr(runtime, "_run_case_command", lambda *args: None)

    runtime.finalize(request_path, state_path, result_path)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["objective"] == 0.75
    assert result["metadata"]["fitness_components"] == {"eta": 0.9}
    assert result["metadata"]["history"]["status"] == "evaluated"
    assert observed["result_existed_at_cleanup"] is True
    assert observed["cleaned"] == "TISTOS_1"
    assert not (case_dir / "processor0").exists()


def test_finalize_failure_preserves_case_and_writes_no_result(
    monkeypatch, tmp_path
):
    request_path = tmp_path / "request.json"
    state_path = tmp_path / "state.json"
    result_path = tmp_path / "result.json"
    work_dir = tmp_path / "work"
    case_dir = work_dir / "case"
    case_dir.mkdir(parents=True)
    _write_request(request_path, "candidate", {}, tmp_path, 1)
    state_path.write_text(
        json.dumps(
            {
                "candidate_id": "candidate",
                "state": "TISTOS_1",
                "vector": [],
                "mpi_ranks": 1,
                "work_dir": str(work_dir),
                "case_dir": str(case_dir),
            }
        ),
        encoding="utf-8",
    )
    observed = {}

    class FakeEvaluation:
        def __init__(self, vector, state):
            del vector, state
            self.history_ = {}

        def evaluate(self):
            raise RuntimeError("post-processing failed")

    class FakeImplementation:
        tistos = FakeEvaluation

        @staticmethod
        def cleanupTistos(state):
            observed["cleaned"] = state

    monkeypatch.setattr(
        runtime, "_load_implementation", lambda staged: FakeImplementation
    )

    with pytest.raises(RuntimeError, match="post-processing failed"):
        runtime.finalize(request_path, state_path, result_path)

    assert case_dir.is_dir()
    assert not result_path.exists()
    assert "cleaned" not in observed


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


def test_runtime_check_distinguishes_required_and_parallel_tools(monkeypatch):
    monkeypatch.setattr(runtime_check, "import_module", lambda name: object())
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


@pytest.mark.parametrize("passed, expected", [(False, 1), (True, 0)])
def test_runtime_cli_exit_status(monkeypatch, passed, expected):
    monkeypatch.setattr(
        "tistos_opt.cli.run_checks",
        lambda: [CheckResult("import dtOOPythonSWIG", passed)],
    )

    assert cli_main(["check-runtime"]) == expected


def _parameter_values():
    return {
        parameter.name: (parameter.lower_bound + parameter.upper_bound) / 2
        for parameter in PARAMETERS
    }


def _write_request(path, candidate_id, parameters, scratch_dir, mpi_ranks):
    path.write_text(
        json.dumps(
            {
                "candidate": {
                    "id": candidate_id,
                    "parameters": parameters,
                },
                "context": {
                    "scratch_dir": str(scratch_dir),
                    "resources": {"mpi_ranks": mpi_ranks},
                },
            }
        ),
        encoding="utf-8",
    )


def _write_case_files(case_dir):
    (case_dir / "system").mkdir(parents=True)
    (case_dir / "constant").mkdir()
    (case_dir / "system" / "controlDict").write_text(
        "endTime 1000;\nwriteInterval 500;\n", encoding="utf-8"
    )
    (case_dir / "system" / "decomposeParDict").write_text(
        "numberOfSubdomains 8;\nmethod simple;\n", encoding="utf-8"
    )
    (case_dir / "system" / "fvSchemes").write_text(
        "default cellLimited Gauss linear 0.33;\n", encoding="utf-8"
    )
    (case_dir / "constant" / "turbulenceProperties").write_text(
        "turbulence on;\n", encoding="utf-8"
    )


def _read_control(case_dir):
    return (case_dir / "system" / "controlDict").read_text(encoding="utf-8")


def _read_decompose(case_dir):
    return (case_dir / "system" / "decomposeParDict").read_text(
        encoding="utf-8"
    )


def _read_turbulence(case_dir):
    return (case_dir / "constant" / "turbulenceProperties").read_text(
        encoding="utf-8"
    )


def _read_schemes(case_dir):
    return (case_dir / "system" / "fvSchemes").read_text(encoding="utf-8")
