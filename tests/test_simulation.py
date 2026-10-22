"""Check the installed-code boundary without requiring dtOO or OpenFOAM."""

import importlib
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from tistos_opt import runtime
from tistos_opt._legacy import sim_tistos
from tistos_opt.case import PARAMETERS


def parameter_values():
    return {
        parameter.name: (parameter.lower_bound + parameter.upper_bound) / 2
        for parameter in reversed(PARAMETERS)
    }


def test_preparation_maps_names_and_isolates_candidates(monkeypatch, tmp_path):
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-2] == "mesh":
            case_dir = kwargs["cwd"] / f"tistos_ru_of_n_{command[-1]}"
            for name in ("system", "constant", "0"):
                (case_dir / name).mkdir(parents=True)

    monkeypatch.setattr(sim_tistos.subprocess, "run", run)
    values = parameter_values()
    work_dirs = []
    for index in range(2):
        work_dir = runtime._stage_case(tmp_path / str(index))
        work_dirs.append(work_dir)
        parameters = dict(values)
        parameters["alpha_1_span_0"] += index * 0.01
        history = sim_tistos.prepare_case(work_dir, "TISTOS_1", parameters)
        state = ET.parse(work_dir / "TISTOS_1.xml").find("state")
        assert state.attrib["label"] == "TISTOS_1"
        for parameter in PARAMETERS:
            element = state.find(
                f"constValue[@label='{parameter.legacy_label}']"
            )
            assert float(element.attrib["value"]) == parameters[parameter.name]
        assert set(history) == {"DateOfBirth", "DateOfCreation"}
        assert Path.cwd() == unrelated

    assert len(calls) == 4
    for (command, kwargs), operation, work_dir in zip(
        calls,
        ("state", "mesh") * 2,
        [w for w in work_dirs for _ in range(2)],
        strict=True,
    ):
        assert command == [
            sys.executable,
            "-m",
            "tistos_opt._legacy.tistos_files.createStatesAndMeshes",
            operation,
            "TISTOS_1",
        ]
        # Inherit stdout/stderr so errors reach backend stage logs.
        assert kwargs == {"cwd": work_dir, "timeout": 300, "check": True}
    assert (work_dirs[0] / "TISTOS_1.xml").read_bytes() != (
        work_dirs[1] / "TISTOS_1.xml"
    ).read_bytes()


@pytest.mark.parametrize("failure", ["command", "timeout", "missing_mesh"])
def test_preparation_failure_propagates(monkeypatch, tmp_path, failure):
    work_dir = runtime._stage_case(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if failure == "command":
            raise subprocess.CalledProcessError(1, command)
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 300)

    monkeypatch.setattr(sim_tistos.subprocess, "run", run)
    error = {
        "command": subprocess.CalledProcessError,
        "timeout": subprocess.TimeoutExpired,
        "missing_mesh": RuntimeError,
    }[failure]
    with pytest.raises(error):
        sim_tistos.prepare_case(work_dir, "TISTOS_1", parameter_values())
    assert len(calls) == (2 if failure == "missing_mesh" else 1)
    assert (work_dir / "TISTOS_1.xml").is_file()


def test_cleanup_uses_explicit_paths_and_preserves_other_files(tmp_path):
    work_dir = runtime._stage_case(tmp_path)
    for name in ("TISTOS_1.xml", "TISTOS_1_mesh.msh", "TISTOS_2.xml"):
        (work_dir / name).touch()
    (work_dir / "tistos_ru_of_n_TISTOS_1").mkdir()
    sim_tistos.cleanup_case(work_dir, "TISTOS_1")
    assert not (work_dir / "TISTOS_1.xml").exists()
    assert not (work_dir / "TISTOS_1_mesh.msh").exists()
    assert not (work_dir / "tistos_ru_of_n_TISTOS_1").exists()
    assert (work_dir / "TISTOS_2.xml").exists()
    assert (work_dir / "tistos_files" / "machine.xml").is_file()


def test_geometry_cli_dispatches_without_embedded_python(monkeypatch):
    names = (
        "baseContainer",
        "dtXmlParser",
        "labeledVectorHandlingAnalyticFunction",
        "labeledVectorHandlingAnalyticGeometry",
        "labeledVectorHandlingBoundedVolume",
        "labeledVectorHandlingConstValue",
        "labeledVectorHandlingDtCase",
        "labeledVectorHandlingDtPlugin",
    )
    monkeypatch.setitem(
        sys.modules,
        "dtOOPythonSWIG",
        SimpleNamespace(**dict.fromkeys(names, object())),
    )
    name = "tistos_opt._legacy.tistos_files.createStatesAndMeshes"
    # Restore module state after testing so fake bindings cannot leak.
    monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module(name)
    calls = []
    monkeypatch.setattr(
        module.createStatesAndMeshes,
        "CreateStates",
        lambda self, state: calls.append(("state", state)),
    )
    monkeypatch.setattr(
        module.createStatesAndMeshes,
        "CreateMeshes",
        lambda self, state, case: calls.append(("mesh", state, case)),
    )
    assert module.main(["state", "TISTOS_1"]) == 0
    assert module.main(["mesh", "TISTOS_1"]) == 0
    assert calls == [
        ("state", "TISTOS_1"),
        ("mesh", "TISTOS_1", "tistos_ru_of"),
    ]
    del sys.modules[name]


def test_runtime_import_has_no_cfd_dependencies_or_file_side_effects(tmp_path):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        str(Path(path).resolve()) for path in sys.path if path
    )
    subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
sys.modules["dtOOPythonSWIG"] = None
sys.modules["pyDtOO"] = None
import tistos_opt.runtime
import tistos_opt.stages
import tistos_opt._legacy
import tistos_opt._legacy.tistos_files
""",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )
    assert list(tmp_path.iterdir()) == []
