"""Validated solver settings shared by case discovery and runtime stages."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SolverOptions:
    """Iteration counts for each stage of the steady solver."""

    laminar_iterations: int = 100
    turbulent_iterations: int = 400

    @property
    def end_time(self) -> int:
        """Return the cumulative iteration at the end of both stages."""
        return self.laminar_iterations + self.turbulent_iterations

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "SolverOptions":
        """Read case options, rejecting nonpositive or noninteger counts."""
        defaults = cls()
        values = {}
        for name in ("laminar_iterations", "turbulent_iterations"):
            value = options.get(name, getattr(defaults, name))
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
            ):
                raise ValueError(
                    f"case.options.{name} must be a positive integer"
                )
            values[name] = value
        return cls(**values)
