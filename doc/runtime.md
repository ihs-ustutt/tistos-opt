# Runtime requirements

Install the package in the Python environment used by dtOO:

```bash
python -m pip install -e .
```

The external runtime must provide:

- the `dtOOPythonSWIG` and `pyDtOO` Python modules;
- the OpenFOAM commands `simpleFoam` and `checkMesh`;
- a working OpenFOAM environment and compatible dtOO libraries.

Parallel evaluations additionally need `decomposePar` and `reconstructPar`. Local parallel execution needs `mpiexec`; Slurm execution uses the `srun` provided by the allocation instead.

## Check the environment

```bash
tistos-opt check-runtime
```

The command checks Python imports, executable discovery, the bundled legacy implementation, and essential case data. Missing requirements are reported as `FAIL`. Missing MPI and decomposition tools are reported as `WARN` because a serial evaluation does not use them.

The report also prints `TMPDIR`, `PYTHONPATH`, and `LD_LIBRARY_PATH`, which are often relevant when diagnosing dtOO installations.

## Packaged case data

The wheel contains:

- `_legacy/sim_tistos.py` and its helper files;
- dtOO and OpenFOAM XML input under `_case_data/xml`;
- inlet boundary data under `_case_data/boundaryData_RU_INLET`.

At runtime these resources must be available as ordinary files in an unpacked installation. Python modules are imported from that installation. Only the XML templates, XML input tree, and boundary data are copied into each candidate's scratch directory.

## How the runtime fits together

Start in `case.py`: `TistosCase.evaluation_plan` describes five ordered commands without importing dtOO. The backend executes them in separate processes; `stages.py` dispatches the three Python commands to `runtime.py`.

| Stage | Responsibility |
| --- | --- |
| `prepare` | Copy packaged inputs into candidate scratch space, generate geometry and mesh, check/decompose the mesh, configure the laminar solve, and save state |
| `solve-laminar` | Run `simpleFoam` with the backend's requested process/thread counts |
| `configure-turbulent` | Update the prepared case for the second solve |
| `solve-turbulent` | Run `simpleFoam` again with the same resources |
| `finalize` | Reconstruct parallel output, read results from the case directory, compute/write the objective with preparation history, and clean generated files |

There are three distinct JSON files:

- `request.json` is written by hydroflow-opt and contains candidate parameters, case options, paths, and resources.
- `tistos-state.json` is written by `prepare` and read by later Python stages. It holds candidate identity, the state label, MPI ranks, generated paths, solver settings, and preparation history. No Python object needs restoring. Older state files containing a parameter vector or mesh path remain readable.
- `result.json` contains the objective and metadata consumed by hydroflow-opt.
  `finalize` writes it before cleaning generated files.

In `runtime.py`, read the three public functions first. The private helpers handle OpenFOAM configuration, data copying, and state JSON. Preparation calls `prepare_case(work_dir, state, parameters)` with named inputs. Finalization calls `evaluate_case(case_dir, options, history)`, which returns JSON-ready objective, components, and history.

Geometry and meshing run as two separate `python -m` child processes, each with the candidate work directory as its `cwd`. This preserves dtOO parser isolation and the relative paths in the XML inputs. Preparation propagates command failures and timeouts to the backend. Postprocessing retains the established penalty objective of `3.0` for invalid results and records the reason in history.

## Build these docs

Install the documentation dependencies and build HTML locally:

```bash
python -m pip install -v -e .[docs]
sphinx-build -W -b html doc doc/build/html
```

Open `doc/build/html/index.html` in a browser.
