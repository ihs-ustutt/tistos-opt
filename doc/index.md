# tistos-opt

`tistos-opt` packages the TiStoS dtOO/OpenFOAM case as a plugin for `hydroflow-opt`. It defines the 30 optimization parameters and the commands that turn one candidate into a scalar objective.

```{toctree}
:maxdepth: 2

overview
evaluation
parameters
configuration
runtime
output-files
api
```

## First run

Check the external simulation environment, then run the supplied candidate:

```bash
tistos-opt check-runtime
hydroflow-opt check examples/tistos_candidate.toml
hydroflow-opt run examples/tistos_candidate.toml
```

See {doc}`evaluation` for the five evaluation stages and {doc}`runtime` for the required dtOO and OpenFOAM installation.
