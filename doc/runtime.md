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

At runtime these resources must be available as ordinary files in an unpacked installation. They are copied into each candidate's scratch directory before the legacy implementation is imported.

## Build these docs

Install the documentation dependencies and build HTML locally:

```bash
python -m pip install -e '.[docs]'
sphinx-build -W -b html doc doc/build/html
```

Open `doc/build/html/index.html` in a browser.
