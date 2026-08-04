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

### Post-process a completed case

Extensions that need CFD files before cleanup can use the context-managed
runtime API:

```python
from tistos_opt import evaluation_session

with evaluation_session(request) as result:
    consume_flow_fields(
        case_dir=result.case_dirs["n"],
        mesh_path=result.mesh_path,
    )
```

Generated case files remain available inside the context and are cleaned after
a successful exit. CFD failures and exceptions raised by the consumer preserve
scratch files for diagnosis. The paths exposed by `result` must not be used
after leaving the context.

## Slurm execution

Select the backend in either candidate or optimization configuration:

```toml
[execution]
backend = "slurm"
```

Run `hydroflow-opt` inside an existing `sbatch` or `salloc` allocation. The
allocation may span nodes, but each candidate must fit on one node.
The TiStoS worker is a controller: geometry generation and meshing run once,
while each OpenFOAM solver stage is launched directly as:

```text
srun --exclusive --nodes=1 --ntasks=<mpi_ranks> \
  --cpus-per-task=<threads_per_rank> --cpu-bind=cores --mpi=pmix \
  simpleFoam -parallel -fileHandler collated
```

There is no nested `mpiexec` in Slurm mode. Local execution continues to use
`mpiexec -n <mpi_ranks>`. For four islands with two one-thread MPI ranks per
candidate, configure:

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

Do not wrap `hydroflow-opt` itself in `srun`; the backend creates the solver
steps from inside the allocation. Controller processes originate on the batch
node; only their scheduler-managed solver stages are placed across multiple
nodes.
