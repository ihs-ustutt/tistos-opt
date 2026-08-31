# Parameters

The parameter space contains ten blade quantities at three normalized span positions: `0`, `0.5`, and `1`. Names use the suffixes `_span_0`, `_span_05`, and `_span_1`.

| Name root | Span 0 bounds | Span 0.5 bounds | Span 1 bounds |
|---|---:|---:|---:|
| `alpha_1` | -0.155, 0.025 | -0.19, -0.01 | -0.19, -0.01 |
| `alpha_2` | -0.08, 0.10 | -0.08, 0.10 | -0.08, 0.07 |
| `offset_m` | 1.0, 1.5 | 1.0, 1.5 | 1.0, 1.5 |
| `ratio` | 0.4, 0.6 | 0.4, 0.6 | 0.4, 0.6 |
| `offset_phi_r` | -0.15, 0.15 | -0.15, 0.15 | -0.15, 0.15 |
| `blade_length` | 0.4, 0.8 | 0.6, 1.0 | 0.8, 1.3 |
| `t_le` | 0.005, 0.06 | 0.005, 0.06 | 0.005, 0.06 |
| `t_mid` | 0.005, 0.06 | 0.005, 0.06 | 0.005, 0.06 |
| `t_te` | 0.005, 0.06 | 0.005, 0.06 | 0.005, 0.06 |
| `u_mid` | 0.4, 0.6 | 0.4, 0.6 | 0.4, 0.6 |

Bounds are inclusive optimizer limits. `TistosCase.parameter_space()` returns the names and bounds in the exact order required by the legacy implementation.  Each name also has a legacy dtOO label, defined together with its bounds in `tistos_opt.case.PARAMETERS`.

The plugin currently ignores `[case.options]`; there are no TiStoS-specific configuration options.
