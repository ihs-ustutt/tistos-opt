# Configuration

TiStoS uses hydroflow-opt's general configuration format. Select the installed plugin with:

```toml
[case]
name = "tistos"
```

## Solver iterations

Set the iteration count for each OpenFOAM stage in the run configuration:

```toml
[case.options]
laminar_iterations = 100
turbulent_iterations = 400
```

Both options must be positive integers. Defaults: the laminar stage stops at iteration 100, then the turbulent stage runs another 400 iterations, ending at 500. For example, values of 200 and 800 stop the stages at 200 and 1000. These counts are independent of optimizer `generations`.

The plugin updates `endTime` and `writeInterval` for each stage and passes the same limits to post-processing, including its result-directory selection and final-iteration check. The settings are saved in `tistos-state.json` and result metadata. The objective averages the final 10% of the cumulative iteration
count, limited to the turbulent-stage length and at least one sample.

## Candidate run

The complete supplied design is in `examples/tistos_candidate.toml`:

```bash
hydroflow-opt check examples/tistos_candidate.toml
hydroflow-opt run examples/tistos_candidate.toml
```

The important run and resource fields are:

```toml
[run]
directory = "runs/tistos_candidate"
scratch_directory = "runs/tistos_candidate/scratch"

[resources]
available_cpus = 8
concurrent_evaluations = 4
mpi_ranks = 2
threads_per_rank = 1
```

This permits four concurrent candidates, each with two MPI ranks. The required CPU constraint is:

```text
concurrent_evaluations × mpi_ranks × threads_per_rank ≤ available_cpus
```

## Optimization

Start the supplied one-island example with:

```bash
hydroflow-opt optimize examples/tistos_optimization.toml
```

The optimizer obtains all names and bounds from the plugin. General optimization settings, checkpointing, and resume behavior belong to hydroflow-opt.

## Slurm

Select Slurm explicitly:

```toml
[execution]
backend = "slurm"
```

Run hydroflow-opt inside an existing `sbatch` or `salloc` allocation. Do not wrap `hydroflow-opt` itself in `srun`; the backend creates one job step for each stage. The run and scratch directories must be visible from every allocated node.

`examples/tistos_candidate_slurm.toml` is a two-rank example. Each candidate must fit on one node even when the outer allocation spans multiple nodes.
