`postprocessing.json` records outputs from the bundled `tistosPyBib.py` before
the runtime simplification. It uses the deterministic readers and residual
files in `test_postprocessing.py`, with timestamps fixed for comparison.

The four cases cover valid output, an incomplete solve, pump detection, and
missing output. They preserve the objective, fitness components, residual
samples, and history. These are numerical unit fixtures, not CFD reference runs.
