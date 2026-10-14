"""Numerical regression against outputs captured before the refactor."""

import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tistos_opt import runtime
from tistos_opt.options import SolverOptions

SCENARIOS = ("valid", "incomplete", "pump", "missing")


def fake_readers(scenario):
    class Developing:
        def __init__(self, path):
            self.path = str(path)

        def Read(self, *args):
            if scenario == "missing":
                raise FileNotFoundError("missing solver output")
            return self.path

    class Scalar:
        def __init__(self, path):
            self.path = path

        def MeanLast(self, count):
            values = {
                "Q_ru_in": 0.2,
                "ptot_ru_in": 40.0,
                "ptot_ru_out": 20.0,
                "V_CAV": 0.0000002,
            }
            return np.float64(
                next(
                    value
                    for name, value in values.items()
                    if name in self.path
                )
            )

        def Mean(self, timestep, count):
            return self.MeanLast(count)

        def LastTime(self):
            return 59 if scenario == "incomplete" else 60

    class Force:
        def __init__(self, path):
            pass

        def MomentMeanLast(self, count):
            return np.array([0.0, 0.0, 1000.0 if scenario == "pump" else 10.0])

        def MomentMean(self, timestep, count):
            return self.MomentMeanLast(count)

    return SimpleNamespace(
        dtDeveloping=Developing,
        dtScalarDeveloping=Scalar,
        dtForceDeveloping=Force,
    )


def write_residuals(case_dir):
    # Exercise the real residual reader on both sides of the laminar boundary.
    for start, count, columns, indices in (
        (0, 20, 15, (3, 6, 9, 14)),
        (20, 40, 25, (3, 6, 9, 24, 14, 19)),
    ):
        names = [f"unused_{index}" for index in range(columns)]
        names[0] = "Time"
        for index, name in zip(
            indices,
            (
                "Ux_final",
                "Uy_final",
                "Uz_final",
                "p_final",
                "k_final",
                "omega_final",
            ),
            strict=False,  # The laminar case has only four residual columns.
        ):
            names[index] = name
        rows = np.zeros((count, columns))
        rows[:, 0] = np.arange(start + 1, start + count + 1)
        for index in indices:
            rows[:, index] = index / 1000
        path = case_dir / f"postProcessing/residuals/{start}/solverInfo.dat"
        path.parent.mkdir(parents=True)
        np.savetxt(path, rows, header="solver residuals\n" + " ".join(names))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_postprocessing_matches_pre_refactor_results(
    monkeypatch, tmp_path, scenario
):
    monkeypatch.setitem(sys.modules, "pyDtOO", fake_readers(scenario))
    monkeypatch.setattr("time.ctime", lambda: "fixed timestamp")
    module = runpy.run_path(
        str(runtime._package_root() / "_legacy/tistos_files/tistosPyBib.py")
    )
    case_dir = tmp_path / "case"
    write_residuals(case_dir)
    preparation = {"DateOfBirth": "prepared", "DateOfCreation": "meshed"}
    objective, extra, history = module["evaluate_case"](
        case_dir,
        SolverOptions(20, 40),
        preparation,
    )
    actual = {"objective": objective, "extra": extra, "history": history}
    expected = json.loads(
        (Path(__file__).parent / "fixtures/postprocessing.json").read_text()
    )[scenario]
    assert actual == expected
    assert type(objective) is float
    assert all(type(extra[key]) is float for key in ("dH", "eta", "VCav", "P"))
    assert json.loads(json.dumps(actual)) == expected
    assert preparation == {
        "DateOfBirth": "prepared",
        "DateOfCreation": "meshed",
    }
