import foamlib as fl
import shutil
import glob
# from utils import *
# logger = import_logger()


def sim_tistos(foamCaseDir, procPerJob):
    # logger.info("Start Sim Tistos OpenFoam")
    fc = fl.FoamCase(foamCaseDir)
    fc.control_dict["functions"].update(
        {
            "residuals": {
                "type": "solverInfo",
                "functionObjectLibs": ["libutilityFunctionObjects.so"],
                "enabled": "true",
                "outputControl": "timeStep",
                "writeControl": "timeStep",
                "outputInterval": 1,
                "log": "yes",
                "timeStart": 0,
                "fields": ["p", "U", "k", "omega"],
            }
        }
    )
    if type(procPerJob) == str:
        int_procPerJob = int(procPerJob)
        str_procPerJob = procPerJob
    elif type(procPerJob) == int:
        int_procPerJob = procPerJob
        str_procPerJob = str(procPerJob)
    fc.decompose_par_dict["numberOfSubdomains"] = int_procPerJob
    fc.decompose_par_dict["method"] = "scotch"
    fc.decompose_par()

    fc.turbulence_properties["RAS"]["turbulence"] = False
    fc.control_dict["endTime"] = 100
    fc.control_dict["writeInterval"] = 100
    fc.run(
        ["mpiexec", "--oversubscribe", "-n", str_procPerJob, "simpleFoam", "-parallel"]
    )

    fc.turbulence_properties["RAS"]["turbulence"] = True
    fc.control_dict["endTime"] = 1000
    fc.control_dict["writeInterval"] = 1000
    fc.run(
        ["mpiexec", "--oversubscribe", "-n", str_procPerJob, "simpleFoam", "-parallel"]
    )
    fc.reconstruct_par()
    processor_dirs = glob.glob("processor*", recursive=False)
    for di in processor_dirs:
        shutil.rmtree(di)
