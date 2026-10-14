import json
import runpy
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace

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


@pytest.mark.parametrize(
    "options, laminar_end, end_time",
    [
        ({}, 100, 500),
        ({"laminar_iterations": 37, "turbulent_iterations": 86}, 37, 123),
    ],
)
def test_prepare_maps_parameters_and_configures_laminar_case(
    monkeypatch, tmp_path, options, laminar_end, end_time
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

    def prepare_case(work, state_label, parameters):
        observed["work_dir"] = work
        observed["parameters"] = parameters
        observed["state"] = state_label
        return {"status": "meshed"}

    commands = []
    monkeypatch.setattr(runtime, "_stage_case", lambda scratch: work_dir)
    monkeypatch.setattr(runtime, "prepare_case", prepare_case)
    monkeypatch.setattr(
        runtime,
        "_run_case_command",
        lambda case, command, log: commands.append((case, command, log)),
    )
    values = _parameter_values()
    _write_request(request_path, candidate_id, values, scratch_dir, 4, options)

    runtime.prepare(request_path, state_path)

    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    assert observed["parameters"] == values
    assert observed["work_dir"] == work_dir
    assert observed["state"] == state
    assert "vector" not in state_data
    assert "mesh_path" not in state_data
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
    assert f"endTime {laminar_end};" in _read_control(case_dir)
    assert f"writeInterval {laminar_end};" in _read_control(case_dir)
    assert "turbulence off;" in _read_turbulence(case_dir)
    assert "faceL" in _read_schemes(case_dir)

    runtime.configure_turbulent(state_path)

    assert f"endTime {end_time};" in _read_control(case_dir)
    assert f"writeInterval {end_time};" in _read_control(case_dir)
    assert "turbulence on;" in _read_turbulence(case_dir)
    assert "cellL" in _read_schemes(case_dir)


def test_configure_turbulent_updates_openfoam_files(tmp_path):
    case_dir = tmp_path / "case"
    _write_case_files(case_dir)
    runtime._configure_laminar(case_dir)

    runtime._configure_turbulent(case_dir)

    assert "endTime 500;" in _read_control(case_dir)
    assert "writeInterval 500;" in _read_control(case_dir)
    assert "turbulence on;" in _read_turbulence(case_dir)
    assert "cellL" in _read_schemes(case_dir)


@pytest.mark.parametrize(
    "options, laminar_end, end_time",
    [
        ({}, 100, 500),
        ({"laminar_iterations": 37, "turbulent_iterations": 86}, 37, 123),
    ],
)
@pytest.mark.parametrize("legacy_state", [False, True])
def test_finalize_writes_result_before_cleanup(
    monkeypatch, tmp_path, options, laminar_end, end_time, legacy_state
):
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
                **(
                    {"vector": [1.0, 2.0], "mesh_path": "old.msh"}
                    if legacy_state
                    else {}
                ),
                "mpi_ranks": 2,
                "work_dir": str(work_dir),
                "case_dir": str(case_dir),
                "history": {"status": "meshed"},
                "solver_options": options,
            }
        ),
        encoding="utf-8",
    )
    observed = {}

    def evaluate_case(case, settings, history):
        observed["case_dir"] = case
        observed["solver_settings"] = settings
        assert history == {"status": "meshed"}
        history["status"] = "evaluated"
        return 0.75, {"eta": 0.9}, history

    def cleanup_case(work, state):
        observed["result_existed_at_cleanup"] = result_path.is_file()
        observed["cleaned"] = state
        assert work == work_dir

    monkeypatch.setitem(
        sys.modules,
        "tistos_opt._legacy.tistos_files.tistosPyBib",
        SimpleNamespace(evaluate_case=evaluate_case),
    )
    monkeypatch.setattr(runtime, "cleanup_case", cleanup_case)
    monkeypatch.setattr(runtime, "_run_case_command", lambda *args: None)

    runtime.finalize(request_path, state_path, result_path)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["objective"] == 0.75
    assert result["metadata"]["fitness_components"] == {"eta": 0.9}
    assert result["metadata"]["history"]["status"] == "evaluated"
    assert observed["result_existed_at_cleanup"] is True
    assert observed["cleaned"] == "TISTOS_1"
    assert observed["case_dir"] == case_dir
    assert observed["solver_settings"].laminar_iterations == laminar_end
    assert observed["solver_settings"].end_time == end_time
    assert result["metadata"]["solver_options"] == {
        "laminar_iterations": laminar_end,
        "turbulent_iterations": end_time - laminar_end,
    }
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

    def evaluate_case(case, options, history):
        raise RuntimeError("post-processing failed")

    monkeypatch.setitem(
        sys.modules,
        "tistos_opt._legacy.tistos_files.tistosPyBib",
        SimpleNamespace(evaluate_case=evaluate_case),
    )
    monkeypatch.setattr(
        runtime, "cleanup_case", lambda *args: observed.update(cleaned=True)
    )

    with pytest.raises(RuntimeError, match="post-processing failed"):
        runtime.finalize(request_path, state_path, result_path)

    assert case_dir.is_dir()
    assert not result_path.exists()
    assert "cleaned" not in observed


def test_stage_case_copies_runtime_assets(tmp_path):
    work_dir = runtime._stage_case(tmp_path)

    assert not list(work_dir.rglob("*.py"))
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


def _write_request(
    path, candidate_id, parameters, scratch_dir, mpi_ranks, options=None
):
    path.write_text(
        json.dumps(
            {
                "candidate": {
                    "id": candidate_id,
                    "parameters": parameters,
                },
                "case": {"name": "tistos", "options": options or {}},
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


@pytest.mark.parametrize(
    "name", ["laminar_iterations", "turbulent_iterations"]
)
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100", None])
def test_invalid_iteration_counts_fail_during_case_validation(name, value):
    with pytest.raises(ValueError, match=f"{name} must be a positive integer"):
        TistosCase().parameter_space({name: value})


@pytest.mark.parametrize(
    "laminar_end, end_time, average, last_time",
    [
        (100, 500, 50, 500),
        (37, 123, 12, 123),
        (1, 2, 1, 2),
        (100, 101, 1, 101),
        (37, 123, 12, 122),
    ],
)
def test_legacy_results_use_configured_limits(
    monkeypatch, tmp_path, laminar_end, end_time, average, last_time
):
    paths = []
    windows = []

    class Developing:
        def __init__(self, path):
            self.path = path
            paths.append(path)

        def Read(self, *args):
            return self.path

    class Scalar:
        def __init__(self, path):
            self.path = path

        def MeanLast(self, count):
            windows.append(count)
            return 2.0 if "ptot_ru_out" in self.path else 1.0

        def LastTime(self):
            return last_time

    class Force:
        def __init__(self, path):
            pass

        def MomentMeanLast(self, count):
            windows.append(count)
            return [0.0, 0.0, 1.0]

    monkeypatch.setitem(
        sys.modules,
        "pyDtOO",
        SimpleNamespace(
            dtDeveloping=Developing,
            dtScalarDeveloping=Scalar,
            dtForceDeveloping=Force,
        ),
    )
    monkeypatch.chdir(tmp_path)
    module = runpy.run_path(
        str(
            runtime._package_root()
            / "_legacy"
            / "tistos_files"
            / "tistosPyBib.py"
        )
    )
    runner = module["tistosRunner"](
        "case_n_TISTOS_1",
        laminar_end_time=laminar_end,
        end_time=end_time,
    )

    history = runner.ReadResults({})

    assert runner.isOk_ == (last_time == end_time)
    if last_time != end_time:
        assert (
            history["ReasonOfFailure"]
            == "Max number of iterations not reached."
        )
    assert paths == [
        f"case_n_TISTOS_1/postProcessing/{name}/{laminar_end}"
        for name in ("Q_ru_in", "ptot_ru_in", "ptot_ru_out", "V_CAV")
    ] + ["case_n_TISTOS_1/postProcessing/forces"]
    assert windows and all(count == average for count in windows)

    sampled = []

    def post_proc(timestep):
        sampled.append(timestep)
        return (
            1,
            1,
            1,
            1,
            dict.fromkeys(
                (
                    "Ux_final",
                    "Uy_final",
                    "Uz_final",
                    "p_final",
                    "k_final",
                    "omega_final",
                ),
                0,
            ),
        )

    runner.post_proc = post_proc
    runner.extract_residuals({})
    assert sampled == list(range(20, end_time + 1, 20))
