"""Read TiStoS solver output and calculate the established objective."""

import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
from pyDtOO import dtDeveloping, dtForceDeveloping, dtScalarDeveloping

from tistos_opt.options import SolverOptions

logger = logging.getLogger(__name__)


def evaluate_case(
    case_dir: Path, options: SolverOptions, history: dict[str, Any]
) -> tuple[float, dict[str, Any], dict[str, Any]]:
    """Return JSON-ready results, preserving preparation and failure history."""
    runner = tistosRunner(
        case_dir,
        laminar_end_time=options.laminar_iterations,
        end_time=options.end_time,
    )
    history = runner.ReadResults(dict(history))
    fitness, extra = runner.GiveFitness()
    logger.info("Fitness for %s: %s", case_dir, fitness)
    return fitness, extra, history


class tistosRunner:
    OMEGA = 7.53982
    DHZUL = -2.4

    def __init__(
        self, case_dir, *,
        laminar_end_time=100, end_time=500,
    ):
        self.case_dir = Path(case_dir)

        self.weights_ = {"tl": 1 / 3, "n": 1, "vl": 1 / 3}
        self.laminar_end_time = laminar_end_time
        self.end_time = end_time

        #
        # Init variables
        #

        self.P_ = {"n": 0}
        self.dH_ = {"n": 0}
        self.eta_ = {"n": 0}
        self.Vcav_ = {"n": 0}

        self.isOk_ = False

    def ReadResults(self, history):
        omega = tistosRunner.OMEGA
        try:
            for i in ["n"]:
                caseDirOf = self.case_dir
                time_step_holder = self.end_time
                #
                # read openFoam results
                #
                Q_ru_dev = dtScalarDeveloping(
                    dtDeveloping(
                        os.path.join(
                            caseDirOf,
                            f"postProcessing/Q_ru_in/{self.laminar_end_time}",
                        )
                    ).Read()
                )
                pIn_ru_dev = dtScalarDeveloping(
                    dtDeveloping(
                        os.path.join(
                            caseDirOf,
                            f"postProcessing/ptot_ru_in/{self.laminar_end_time}",
                        )
                    ).Read()
                )
                pOut_ru_dev = dtScalarDeveloping(
                    dtDeveloping(
                        os.path.join(
                            caseDirOf,
                            f"postProcessing/ptot_ru_out/{self.laminar_end_time}",
                        )
                    ).Read()
                )
                Vcav = dtScalarDeveloping(
                    dtDeveloping(
                        os.path.join(
                            caseDirOf,
                            f"postProcessing/V_CAV/{self.laminar_end_time}",
                        )
                    ).Read()
                )
                F_dev = dtForceDeveloping(
                    dtDeveloping(os.path.join(caseDirOf, "postProcessing/forces")).Read(
                        {"force.dat": ":,4:10", "moment.dat": ":,4:10", "*.*": ""}
                    )
                )

                average_time = max(
                    1,
                    min(
                        time_step_holder // 10,
                        self.end_time - self.laminar_end_time,
                    ),
                )
                self.P_[i] = F_dev.MomentMeanLast(average_time)[2] * omega
                self.dH_[i] = (
                    pOut_ru_dev.MeanLast(average_time)
                    - pIn_ru_dev.MeanLast(average_time)
                ) / 9.81
                self.eta_[i] = self.P_[i] / (
                    1000.0 * 9.81 * self.dH_[i] * Q_ru_dev.MeanLast(average_time)
                )
                self.Vcav_[i] = Vcav.MeanLast(average_time)

                # check for last iteration
                self.lastIt_ = int(pIn_ru_dev.LastTime())
                if self.lastIt_ != time_step_holder:
                    raise ValueError("Max number of iterations not reached.")

                # Throw an error in case of a pump
                if np.abs(self.eta_[i]) > 1:
                    raise ValueError("Pump detected.")
            #
            # toggle isOk to True
            self.isOk_ = True
            history["DateOfEvaluation"] = time.ctime()

        except Exception as e:
            # logger.warning('Catch exception in PostProcessing: %s', e)
            history["DateOfFailure"] = time.ctime()
            history["ReasonOfFailure"] = str(e)
        return history

    def post_proc(self, timestep):
        caseDirOf = self.case_dir
        omega = tistosRunner.OMEGA
        timestep_orig = timestep  # offset because different files...
        if timestep > self.laminar_end_time:
            post_proc_folder = self.laminar_end_time
            timestep_force = timestep
            timestep = timestep - self.laminar_end_time
        else:
            post_proc_folder = 0
            timestep_force = timestep
        Q_ru_dev = dtScalarDeveloping(
            dtDeveloping(
                os.path.join(caseDirOf, f"postProcessing/Q_ru_in/{post_proc_folder}")
            ).Read()
        )
        pIn_ru_dev = dtScalarDeveloping(
            dtDeveloping(
                os.path.join(caseDirOf, f"postProcessing/ptot_ru_in/{post_proc_folder}")
            ).Read()
        )
        pOut_ru_dev = dtScalarDeveloping(
            dtDeveloping(
                os.path.join(
                    caseDirOf, f"postProcessing/ptot_ru_out/{post_proc_folder}"
                )
            ).Read()
        )
        Vcav_ = dtScalarDeveloping(
            dtDeveloping(
                os.path.join(caseDirOf, f"postProcessing/V_CAV/{post_proc_folder}")
            ).Read()
        )
        F_dev = dtForceDeveloping(
            dtDeveloping(os.path.join(caseDirOf, "postProcessing/forces")).Read(
                {"force.dat": ":,4:10", "moment.dat": ":,4:10", "*.*": ""}
            )
        )
        # res = dtDeveloping(
        # os.path.join(caseDirOf, f'postProcessing/residuals/{post_proc_folder}')).Read()
        path_solverInfo = os.path.join(
            caseDirOf, f"postProcessing/residuals/{post_proc_folder}/solverInfo.dat"
        )
        res_names = np.genfromtxt(
            path_solverInfo, names=True, skip_header=1
        ).dtype.names
        res = np.genfromtxt(path_solverInfo)

        average_time = min(10, timestep)
        res_dict = {}
        P = F_dev.MomentMean(timestep_force, average_time)[2] * omega
        dH = (
            pOut_ru_dev.Mean(timestep, average_time)
            - pIn_ru_dev.Mean(timestep, average_time)
        ) / 9.81
        eta = P / (1000.0 * 9.81 * dH * Q_ru_dev.Mean(timestep, average_time))
        Vcav = Vcav_.Mean(timestep, average_time)
        if post_proc_folder == 0:
            # res = res[-1,[3,6,9,14]]
            header_list = [
                "Ux_final",
                "Uy_final",
                "Uz_final",
                "p_final",
            ]  # , 'k_final', 'omega_final']
            indice_list = [3, 6, 9, 14]
            for i, header in enumerate(header_list):
                assert res_names[indice_list[i]] == header, "Header Error"
                res_dict.update({header: float(res[timestep - 1, indice_list[i]])})
                assert res[timestep - 1, 0] == timestep, (
                    f"timestep = {timestep} and time in res = {res[timestep - 1, 0]}"
                )
            res_dict.update(
                {"k_final": 0.0}
            )  # artificial residuals for k, omega in laminar part
            res_dict.update({"omega_final": 0.0})
        else:
            # res = res[-1,[3,6,9,24,14,19]]         #Ux_final, Uy_final, Uz_final, p_final, k_final, omega_final
            header_list = [
                "Ux_final",
                "Uy_final",
                "Uz_final",
                "p_final",
                "k_final",
                "omega_final",
            ]
            indice_list = [3, 6, 9, 24, 14, 19]
            for i, header in enumerate(header_list):
                assert res_names[indice_list[i]] == header, "Header Error"
                res_dict.update({header: float(res[timestep - 1, indice_list[i]])})
                assert res[timestep - 1, 0] == timestep_orig, (
                    f"timestep = {timestep} and time in res = {res[timestep - 1, 0]}"
                )
        return float(P), float(dH), float(eta), float(Vcav), res_dict

    def GiveFitness(self):
        dHZul = tistosRunner.DHZUL
        fitnessEta, fitnessVcav, fitnessH = 0.0, 0.0, 0.0
        if self.isOk_:
            # Preserve the established efficiency, cavitation, and head terms.
            for i in "n":
                fitnessEta += self.weights_[i] * np.abs(1 + self.eta_[i])
                fitnessVcav += self.weights_[i] * self.Vcav_[i]
            fitnessH = np.abs(self.dH_["n"] - dHZul)
            ### single objective fitness ###
            fitness = (
                np.tanh(fitnessEta) + np.tanh(fitnessVcav * 1e6) + np.tanh(fitnessH)
            )
        else:
            fitness = 3.0
        fitness_extra = {
            "dH": float(self.dH_["n"]),
            "eta": float(self.eta_["n"]),
            "VCav": float(self.Vcav_["n"]),
            "P": float(self.P_["n"]),
        }
        self.extract_residuals(fitness_extra)
        return float(fitness), fitness_extra

    def extract_residuals(self, fitness_extra):
        ### get residuals and stuff
        res = []
        P = []
        dH = []
        eta = []
        Vcav = []
        Ux_final = []
        Uy_final = []
        Uz_final = []
        p_final = []
        k_final = []
        omega_final = []
        time_list = []
        end_time = self.end_time
        for timestep in range(20, end_time + 1, 20):
            try:
                P_temp, dH_temp, eta_temp, Vcav_temp, res = self.post_proc(timestep)
                P.append(P_temp)
                dH.append(dH_temp)
                eta.append(eta_temp)
                Vcav.append(Vcav_temp)
                time_list.append(int(timestep))
                Ux_final.append(res["Ux_final"])
                Uy_final.append(res["Uy_final"])
                Uz_final.append(res["Uz_final"])
                p_final.append(res["p_final"])
                k_final.append(res["k_final"])
                omega_final.append(res["omega_final"])
            except IndexError:
                if self.isOk_:
                    logger.exception("Index Error")
                break
            except:
                if self.isOk_:
                    logger.exception("Extract_Residuals Exception")
                break
        fitness_extra.update(
            {
                "res": {
                    "time": time_list,
                    "P": P,
                    "dH": dH,
                    "eta": eta,
                    "Vcav": Vcav,
                    "Ux_final": Ux_final,
                    "Uy_final": Uy_final,
                    "Uz_final": Uz_final,
                    "p_final": p_final,
                    "k_final": k_final,
                    "omega_final": omega_final,
                }
            }
        )
