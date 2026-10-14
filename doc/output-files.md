# Output files

Hydroflow-opt owns the run and evaluation records. For the candidate `author-example`, the TiStoS-specific additions are:

```text
run-directory/
├── evaluations/
│   └── author-example/
│       ├── request.json
│       ├── result.json
│       ├── tistos-state.json
│       └── stages/
│           ├── 01-prepare/
│           ├── 02-solve-laminar/
│           ├── 03-configure-turbulent/
│           ├── 04-solve-turbulent/
│           └── 05-finalize/
└── scratch/
    └── author-example/
        └── tistos/
```

Each stage directory contains hydroflow-opt's `metadata.json`, `stdout.log`, and `stderr.log`. Commands launched inside the TiStoS runtime also create OpenFOAM logs such as `log.checkMesh`, `log.decomposePar`, and `log.reconstructPar` in the generated case directory. Python diagnostics and geometry/meshing subprocess output go to the backend stage logs. There is no separate `tistos.log`.

## Result metadata

On success, `result.json` contains the scalar objective plus:

```json
{
  "metadata": {
    "state": "TISTOS_123456789",
    "fitness_components": {},
    "history": {}
  }
}
```

`fitness_components` and `history` contain the JSON-compatible values returned by the legacy post-processing code. Hydroflow-opt adds measured stage timings and backend metadata.

Successful finalization removes generated state, mesh, processor, and CFD case files while retaining the normalized result. Failed evaluations retain the scratch case for inspection.
