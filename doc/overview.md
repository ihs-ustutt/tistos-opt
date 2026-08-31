# Overview

TiStoS is a case plugin, not an optimizer or execution backend. Its responsibilities are:

- expose the 30 design parameters and their physical bounds;
- map their readable names to the labels expected by the legacy case;
- create an isolated dtOO/OpenFOAM case for each candidate;
- declare the serial and parallel evaluation stages;
- calculate and write the final objective and case metadata.

`hydroflow-opt` supplies candidate generation, concurrency, local or Slurm launching, stage logs, result validation, and optimization checkpoints.

## Data flow

```text
named candidate parameters
          │
          ▼
TiStoS parameter vector ──> dtOO geometry and mesh
                                  │
                                  ▼
                         laminar simpleFoam
                                  │
                                  ▼
                        turbulent simpleFoam
                                  │
                                  ▼
                    post-processing ──> objective
```

The package registers `TistosCase` under the entry-point name `tistos`. Importing the plugin does not import dtOO or OpenFOAM-related Python modules; those dependencies are loaded only inside evaluation subprocesses.

## Candidate isolation

Every candidate receives its own scratch tree. The plugin copies the bundled legacy implementation, XML input, and boundary data into that tree before loading dtOO. Candidates therefore do not share mutable case files and can be evaluated concurrently.
