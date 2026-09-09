# Evaluation stages

`TistosCase.evaluation_plan()` returns five ordered stages:

| Stage | Work performed | Resources |
|---|---|---|
| `prepare` | Copy packaged inputs, map the candidate vector, run dtOO geometry and meshing, run `checkMesh`, optionally decompose the case, and select laminar settings | one process |
| `solve-laminar` | Run `simpleFoam` to iteration 100 by default | configured MPI ranks and threads |
| `configure-turbulent` | Enable turbulence, change the end time to 500, and update discretization settings | one process |
| `solve-turbulent` | Continue `simpleFoam` to iteration 500 by default | configured MPI ranks and threads |
| `finalize` | Optionally reconstruct, post-process, write the objective and metadata, then clean generated case files | one process |

Stages run sequentially for one candidate. Different candidates, including their `prepare` stages, run concurrently up to `resources.concurrent_evaluations`. Preparation itself is serial because the legacy dtOO workflow is not internally parallel.

## Commands and resource translation

The plugin declares the solver simply as `simpleFoam`. With more than one MPI rank it adds:

```text
simpleFoam -parallel -fileHandler collated
```

It does not add `mpiexec` or `srun`. Hydroflow-opt translates the declared stage resources for the selected backend:

- local multi-rank stages use `mpiexec -n <mpi_ranks>`;
- Slurm stages use exclusive `srun` job steps;
- serial stages run directly locally or as one-task Slurm steps.

## State passed between stages

`prepare` writes `tistos-state.json` in the evaluation directory. It records the candidate ID, legacy state label, ordered parameter vector, MPI rank count, generated paths, and dtOO history. Later stages read this file rather than relying on in-memory Python state.

## Failures and cleanup

A failing command stops the evaluation. Hydroflow-opt records the failed stage and creates a failed result. The plugin does not clean a failed case, leaving its scratch files available for diagnosis.

On success, `finalize` writes `result.json` before calling the legacy cleanup function. This ordering ensures that a cleanup problem cannot erase an otherwise completed objective.

The stage lengths are configurable through `case.options.laminar_iterations` and `case.options.turbulent_iterations`; see {doc}`configuration`. The turbulent count is additional to the laminar count.
