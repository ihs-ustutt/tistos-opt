"""Case declaration for hydroflow-opt without importing CFD dependencies."""

import sys
import zlib
from dataclasses import dataclass
from typing import Any

from hydroflow_opt.models import (
    Candidate,
    EvaluationPaths,
    EvaluationPlan,
    EvaluationStage,
    ParameterSpace,
    ResourceRequest,
    StageResources,
)


@dataclass(frozen=True)
class ParameterDefinition:
    """One named optimizer parameter and its legacy dtOO label."""

    name: str
    legacy_label: str
    lower_bound: float
    upper_bound: float


PARAMETERS = (
    ParameterDefinition(
        "alpha_1_span_0", "cV_ru_alpha_1_ex_0.0", -0.155, 0.025
    ),
    ParameterDefinition(
        "alpha_1_span_05", "cV_ru_alpha_1_ex_0.5", -0.19, -0.01
    ),
    ParameterDefinition(
        "alpha_1_span_1", "cV_ru_alpha_1_ex_1.0", -0.19, -0.01
    ),
    ParameterDefinition("alpha_2_span_0", "cV_ru_alpha_2_ex_0.0", -0.08, 0.1),
    ParameterDefinition("alpha_2_span_05", "cV_ru_alpha_2_ex_0.5", -0.08, 0.1),
    ParameterDefinition("alpha_2_span_1", "cV_ru_alpha_2_ex_1.0", -0.08, 0.07),
    ParameterDefinition("offset_m_span_0", "cV_ru_offsetM_ex_0.0", 1.0, 1.5),
    ParameterDefinition("offset_m_span_05", "cV_ru_offsetM_ex_0.5", 1.0, 1.5),
    ParameterDefinition("offset_m_span_1", "cV_ru_offsetM_ex_1.0", 1.0, 1.5),
    ParameterDefinition("ratio_span_0", "cV_ru_ratio_0.0", 0.4, 0.6),
    ParameterDefinition("ratio_span_05", "cV_ru_ratio_0.5", 0.4, 0.6),
    ParameterDefinition("ratio_span_1", "cV_ru_ratio_1.0", 0.4, 0.6),
    ParameterDefinition(
        "offset_phi_r_span_0", "cV_ru_offsetPhiR_ex_0.0", -0.15, 0.15
    ),
    ParameterDefinition(
        "offset_phi_r_span_05", "cV_ru_offsetPhiR_ex_0.5", -0.15, 0.15
    ),
    ParameterDefinition(
        "offset_phi_r_span_1", "cV_ru_offsetPhiR_ex_1.0", -0.15, 0.15
    ),
    ParameterDefinition(
        "blade_length_span_0", "cV_ru_bladeLength_0.0", 0.4, 0.8
    ),
    ParameterDefinition(
        "blade_length_span_05", "cV_ru_bladeLength_0.5", 0.6, 1.0
    ),
    ParameterDefinition(
        "blade_length_span_1", "cV_ru_bladeLength_1.0", 0.8, 1.3
    ),
    ParameterDefinition("t_le_span_0", "cV_ru_t_le_a_0", 0.005, 0.06),
    ParameterDefinition("t_le_span_05", "cV_ru_t_le_a_0.5", 0.005, 0.06),
    ParameterDefinition("t_le_span_1", "cV_ru_t_le_a_1", 0.005, 0.06),
    ParameterDefinition("t_mid_span_0", "cV_ru_t_mid_a_0", 0.005, 0.06),
    ParameterDefinition("t_mid_span_05", "cV_ru_t_mid_a_0.5", 0.005, 0.06),
    ParameterDefinition("t_mid_span_1", "cV_ru_t_mid_a_1", 0.005, 0.06),
    ParameterDefinition("t_te_span_0", "cV_ru_t_te_a_0", 0.005, 0.06),
    ParameterDefinition("t_te_span_05", "cV_ru_t_te_a_0.5", 0.005, 0.06),
    ParameterDefinition("t_te_span_1", "cV_ru_t_te_a_1", 0.005, 0.06),
    ParameterDefinition("u_mid_span_0", "cV_ru_u_mid_a_0", 0.4, 0.6),
    ParameterDefinition("u_mid_span_05", "cV_ru_u_mid_a_0.5", 0.4, 0.6),
    ParameterDefinition("u_mid_span_1", "cV_ru_u_mid_a_1", 0.4, 0.6),
)


class TistosCase:
    """Expose the TiStoS parameters and staged evaluation workflow."""

    def parameter_space(self, options: dict[str, Any]) -> ParameterSpace:
        """Return the physical optimization bounds for TiStoS."""

        del options
        return ParameterSpace(
            names=tuple(parameter.name for parameter in PARAMETERS),
            lower_bounds=tuple(
                parameter.lower_bound for parameter in PARAMETERS
            ),
            upper_bounds=tuple(
                parameter.upper_bound for parameter in PARAMETERS
            ),
        )

    def evaluation_plan(
        self,
        candidate: Candidate,
        paths: EvaluationPaths,
        resources: ResourceRequest,
    ) -> EvaluationPlan:
        """Return the serial preparation and parallel solver stages."""

        state = _state_label(candidate.id)
        work_dir = paths.scratch_dir / "tistos"
        case_dir = work_dir / f"tistos_ru_of_n_{state}"
        state_path = paths.evaluation_dir / "tistos-state.json"
        python_stage = (sys.executable, "-m", "tistos_opt.stages")
        solver_resources = StageResources(
            processes=resources.mpi_ranks,
            threads_per_process=resources.threads_per_rank,
        )
        solver_command: tuple[str, ...] = ("simpleFoam",)
        if resources.mpi_ranks > 1:
            solver_command += ("-parallel", "-fileHandler", "collated")

        return EvaluationPlan(
            stages=(
                EvaluationStage(
                    name="prepare",
                    command=(
                        *python_stage,
                        "prepare",
                        str(paths.request_path),
                        str(state_path),
                    ),
                    working_directory=paths.scratch_dir,
                ),
                EvaluationStage(
                    name="solve-laminar",
                    command=solver_command,
                    working_directory=case_dir,
                    resources=solver_resources,
                ),
                EvaluationStage(
                    name="configure-turbulent",
                    command=(
                        *python_stage,
                        "configure-turbulent",
                        str(state_path),
                    ),
                    working_directory=case_dir,
                ),
                EvaluationStage(
                    name="solve-turbulent",
                    command=solver_command,
                    working_directory=case_dir,
                    resources=solver_resources,
                ),
                EvaluationStage(
                    name="finalize",
                    command=(
                        *python_stage,
                        "finalize",
                        str(paths.request_path),
                        str(state_path),
                        str(paths.result_path),
                    ),
                    working_directory=work_dir,
                ),
            )
        )


def _state_label(candidate_id: str) -> str:
    """Create the numeric-suffix state label required by legacy TiStoS."""

    number = zlib.crc32(candidate_id.encode("utf-8"))
    return f"TISTOS_{number}"
