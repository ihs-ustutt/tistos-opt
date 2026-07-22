# tistos-opt

[![Build](https://github.com/thomasisensee/tistos-opt/actions/workflows/ci.yml/badge.svg)](https://github.com/thomasisensee/tistos-opt/actions)

`tistos-opt` packages the TiStoS dtOO/OpenFOAM evaluation as a case plugin for
[`hydroflow-opt`](https://pypi.org/project/hydroflow-opt/). The optimizer owns
candidate generation, concurrency, resource accounting, and result storage;
this package supplies the 30-dimensional parameter space and an isolated CFD
worker.

## Installation

Install the Python packages into the environment used by dtOO:

```bash
python -m pip install -e .
```

The external runtime must also provide dtOO and its Python bindings,
OpenFOAM's `simpleFoam` and `checkMesh`, and MPI tools for parallel runs. Check
the active environment with:

```bash
tistos-opt check-runtime
```

## Run the supplied candidate

The candidate configuration reproduces the parameter vector supplied with the
original case:

```bash
hydroflow-opt check examples/tistos_candidate.toml
hydroflow-opt run examples/tistos_candidate.toml
```

Start a pygmo differential-evolution run with:

```bash
hydroflow-opt optimize examples/tistos_optimization.toml
```

Each evaluation receives its own scratch directory. The bundled legacy code,
geometry XML, and OpenFOAM inlet boundary data are copied there before dtOO is
loaded, so concurrent candidates do not share mutable case files.
