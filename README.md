# tistos-opt

[![Build](https://github.com/thomasisensee/tistos-opt/actions/workflows/ci.yml/badge.svg)](https://github.com/thomasisensee/tistos-opt/actions)

`tistos-opt` packages the TiStoS dtOO/OpenFOAM evaluation as a case plugin for [`hydroflow-opt`](https://pypi.org/project/hydroflow-opt/). The optimizer owns candidate generation, concurrency, resource accounting, and result storage; this package supplies the 30-dimensional parameter space and a staged CFD evaluation plan.

The [documentation](doc/index.md) describes the parameters, evaluation stages, runtime requirements, configuration, and output files.

## Installation

Install the Python packages into the environment used by dtOO:

```bash
python -m pip install -e .
```

The external runtime must also provide dtOO and its Python bindings, OpenFOAM's `simpleFoam` and `checkMesh`, and MPI tools for parallel runs. Check the active environment with:

```bash
tistos-opt check-runtime
```

## Run the supplied candidate

The candidate configuration reproduces the parameter vector supplied with the original case:

```bash
hydroflow-opt check examples/tistos_candidate.toml
hydroflow-opt run examples/tistos_candidate.toml
```

Start a pygmo differential-evolution run with:

```bash
hydroflow-opt optimize examples/tistos_optimization.toml
```

Set `laminar_iterations` and `turbulent_iterations` under `[case.options]` to adjust the solver stage counts; see [configuration](doc/configuration.md#solver-iterations).

Each evaluation receives its own scratch directory. The bundled legacy code, geometry XML, and OpenFOAM inlet boundary data are copied there before dtOO is loaded, so concurrent candidates do not share mutable case files.

## Evaluation stages

Each candidate is evaluated as five explicit stages:

1. `prepare` copies the case, generates geometry and mesh, runs `checkMesh`, decomposes parallel cases, and configures the laminar solve.
2. `solve-laminar` runs `simpleFoam` to iteration 100 by default.
3. `configure-turbulent` enables turbulence and changes the end time to 500.
4. `solve-turbulent` continues for another 400 iterations by default (ending at 500).
5. `finalize` reconstructs parallel results, computes the objective, writes the structured result, and cleans generated files after success.

Preparation and configuration use one process; the two solver stages use the configured MPI ranks and threads. Failed evaluations retain their scratch files for diagnosis.

## Slurm execution

Select the backend in either candidate or optimization configuration:

```toml
[execution]
backend = "slurm"
```

Run `hydroflow-opt` inside an existing `sbatch` or `salloc` allocation. The allocation may span nodes, but each candidate must fit on one node. Every stage, including geometry generation and meshing, is launched as an explicit exclusive one-node `srun` step. Serial stages request one task; each OpenFOAM stage is launched as:

```text
srun --exclusive --nodes=1 --ntasks=<mpi_ranks> \
  --cpus-per-task=<threads_per_rank> --cpu-bind=cores --mpi=pmix \
  simpleFoam -parallel -fileHandler collated
```

There is no nested `mpiexec` in Slurm mode. In local mode, hydroflow-opt runs serial stages directly and prefixes multi-process solver stages with `mpiexec -n <mpi_ranks>`. Multiple candidate evaluations can therefore perform meshing concurrently as well as solving concurrently. For four islands with two one-thread MPI ranks per candidate, configure:

```toml
[resources]
available_cpus = 8
concurrent_evaluations = 4
mpi_ranks = 2
threads_per_rank = 1
```

and request:

```bash
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
```

Before a production run, verify that `srun --mpi=list` includes `pmix`.

### Slurm smoke test

The staged example runs the supplied candidate with two OpenFOAM ranks:

```bash
#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread

source /path/to/the/runtime-environment.sh
cd /path/to/tistos-opt

srun --mpi=list
tistos-opt check-runtime
hydroflow-opt check examples/tistos_candidate_slurm.toml
hydroflow-opt run examples/tistos_candidate_slurm.toml
```

Do not wrap `hydroflow-opt` itself in `srun`; the backend creates the stage steps from inside the allocation. The run and scratch directories must be on a filesystem visible from every allocated node because consecutive stages of a candidate are not required to run on the same node.
