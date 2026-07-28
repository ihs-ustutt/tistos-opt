import subprocess
import xml.etree.ElementTree as ET
import os
import sys
import time
from tistos_files.tistosPyBib import *
from tistos_files.createStatesAndMeshes import *
import glob

from logging.handlers import WatchedFileHandler


def import_logger(filename="tistos.log", level=logging.DEBUG):
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    if not logger.handlers:
        filehandler = WatchedFileHandler(filename)
        filehandler.setLevel(level)
        filehandler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s : %(message)s")
        )
        logger.addHandler(filehandler)
    # logger.info(f"Initialized Logger. Filename: {filename}.")
    return logger


logger = import_logger()


class tistos:
    def __init__(self, x, state, solver_launcher=None):
        self.state = state
        self.history_ = {}
        self.history_["DateOfBirth"] = time.ctime()
        self.x = x
        # self.mainDir = os.getcwd()
        self.stateNumber = int(self.state.split("_")[-1])
        self.caseName = "tistos_ru_of"
        self.procPerJob = int(os.environ.get("FLOW_OPT_MPI_RANKS", "1"))
        self.solverLauncher = list(solver_launcher or [])
        self.cfdOk_ = False
        # self.wd = os.environ["TMPDIR"]
        self.wd = "./"
        self.mainDir = self.wd
        os.chdir(self.wd)
        # logger.debug([x[0] for x in os.walk(self.mainDir)])
        # logger.info(f"Changed to dir: {os.getcwd()}.")

    def pre(self):
        self.cVDict = tistosRunner.DoF()
        self.cVStr_ = []
        self.lowB_ = []
        self.upB_ = []
        for i in range(np.size(self.cVDict)):
            self.cVStr_.append(self.cVDict[i]["label"])
            self.lowB_.append(self.cVDict[i]["min"])
            self.upB_.append(self.cVDict[i]["max"])
        self.dim = np.size(self.upB_)
        # logger.info(f"Before ERror: dir: {os.getcwd()}.")
        # self.xmlStateFileStr = os.path.join(self.MainDir ,'/tistos_files/templateState.xml')
        self.xmlStateFileStr = "./tistos_files/templateState.xml"
        x = self.x

        cVStr = self.cVStr_
        # parse
        xmlStateFile = ET.parse(self.xmlStateFileStr)
        # find state label and replace
        stateC = xmlStateFile.find("state")
        stateC.attrib["label"] = self.state
        # find constValues and replace
        aCount = 0
        for aStr in cVStr:
            stateC.find("constValue[@label='" + str(aStr) + "']").attrib["value"] = str(
                x[aCount]
            )
            aCount = aCount + 1

        if os.path.isfile(self.state + ".xml"):
            os.remove(self.state + ".xml")
        xmlStateFile.write(self.state + ".xml")
        logger.info(f"Finished Pre-Processing for State {self.state}.")
        return self.stateNumber

    def mesh(self):
        state = self.state
        mainDir = self.mainDir
        debug_copy_mesh = False
        caseName = self.caseName
        logger.info(f"Start Meshing for State {self.state}.")
        try:
            if debug_copy_mesh:
                logger.info("ONLY COPYING MESH FOR DEBUGGING REASONS...")
                args = [
                    "cp",
                    "-r",
                    f"{mainDir}/tistos_files/dummy_ru_gridGmsh.msh",
                    state + "_ru_gridGmsh.msh",
                ]
                subprocess.call(args, timeout=60)

            # create state and cfd mesh
            # createStatesAndMeshes().CreateStates(state)
            # createStatesAndMeshes().CreateMeshes(state, caseName)
            args = [
                sys.executable,
                "-c",
                "from tistos_files.createStatesAndMeshes import *;"
                "createStatesAndMeshes().CreateStates('" + state + "')",
            ]
            # result_a = subprocess.run(args, capture_output = True, timeout=1200)
            result_a = subprocess.run(
                args, capture_output=True, timeout=300, check=True
            )
            # logger.debug(f"result_a: {result_a.stdout.decode()}.")
            # logger.debug(f"result_a: {result_a.stderr.decode()}.")
            args = [
                sys.executable,
                "-c",
                "from tistos_files.createStatesAndMeshes import *;"
                "createStatesAndMeshes().CreateMeshes('"
                + state
                + "', '"
                + caseName
                + "')",
            ]
            result_b = subprocess.run(
                args, capture_output=True, timeout=300, check=True
            )
            # logger.debug(f"result_b: {result_b.stdout.decode()}.")
            # logger.debug(f"result_b: {result_b.stderr.decode()}.")

            path = caseName + "_n_" + state
            if not (
                os.path.exists(caseName + "_n_" + state)
                and os.path.exists(caseName + "_n_" + state + "/system")
                and os.path.exists(caseName + "_n_" + state + "/constant")
                and os.path.exists(caseName + "_n_" + state + "/0")
            ):
                raise ValueError("CFD-Mesh not written for state: ", state)
            else:
                logger.info(f"Successfully generated Mesh and Directory for {state}.")
                # logger.info(f"Path: {path}")
            self.history_["DateOfCreation"] = time.ctime()
            self.MeshOk_ = True
        except:
            logger.info(f"Failed Meshing for {state}.")
            logger.exception("Exception:")
            logger.info("self.MeshOk_ = False")
            self.MeshOk_ = False

    def run(self):
        logger.info("Start run routine...")
        start_time = time.time()
        state = self.state
        mainDir = self.mainDir
        caseName = self.caseName
        procPerJob = self.procPerJob
        foamCaseDir = os.path.join(mainDir, (caseName + "_n_" + state))
        use_foamlib = True
        # logger.debug(f"SLURM JOB STEP: {os.environ['SLURM_STEPID']}.")
        try:
            if type(procPerJob) == str:
                int_procPerJob = int(procPerJob)
                str_procPerJob = procPerJob
            elif type(procPerJob) == int:
                int_procPerJob = procPerJob
                str_procPerJob = str(procPerJob)
                # shutil.rmtree(di)

            ### openfoam ###
            args = [
                "sh",
                "-e",
                os.path.join(mainDir, "tistos_files/sbatch.tistos_ru_of.sh"),
                foamCaseDir,
                str(procPerJob),
                *self.solverLauncher,
            ]
            logger.info(f"Start CFD for {state}.")
            result = subprocess.run(
                args, text=True, capture_output=True, timeout=15 * 60, check=True
            )
            logger.info(f"Finished CFD for {state}.")

            end_time = time.time()
            # logger.info(f"Results for {state}:" )
            logger.info(f"Results for {state}:{result.returncode}.")
            if result.returncode == 0:
                # logger.debug(f"Time {state}: {round(end_time - start_time,2)}.")
                # logger.debug(f"STD_ERR: {result.stderr}.")
                # logger.debug(f"STD_OUT: {result.stdout}.")
                self.cfdOk_ = True
            else:
                logger.warning(f"Return Code for {state}: {result.returncode}.")
                logger.warning(f"STD_ERR: {result.stderr}.")
                logger.warning(f"STD_OUT: {result.stdout}.")

        except Exception as e:
            logger.warning("Catch exception in sbatch OpenFoam Sim: %s", e)
            logger.exception("this is the exception")
            logger.exception(f"Type: {type(e)}.")
            if isinstance(e, subprocess.CalledProcessError):
                logger.warning("Output des CalledProcessError:")
                logger.warning(e.stderr)
                logger.warning(e.stdout)
            self.history_["DateOfFailure"] = time.ctime()
            self.history_["ReasonOfFailure"] = str(e)

    def evaluate(self):
        try:
            logger.info(f"Pyro: POST PROCESSING {self.state}")
            aProb = tistosRunner(
                case=self.caseName,
                prefix=self.state.split("_")[0],
                stateNumber=self.stateNumber,
                coeff=self.x,
            )
            aProb.ReadResults(self.history_)
            if aProb.isOk_:
                logger.info("StateLabel = %s -> OK", self.state)
            else:
                logger.info("StateLabel = %s -> FAIL", self.state)
                pass
            fit, fit_extra = aProb.GiveFitness()
            logger.info(f"FITNESS of {self.state}: {fit}")
        except:
            if self.cfdOk_:
                logger.exception("Evaluation Exception")
            else:
                pass
        return fit, fit_extra

    def delete(self):
        state = self.state
        case = self.caseName
        copy_failed_logs = True
        ### delete files ###
        try:
            fileList = glob.glob(state + ".*", recursive=False)
            fileList = fileList + glob.glob(state + "_*", recursive=False)
            for i in ["_n_"]:
                fileList.append(case + i + state)
            for filePath in fileList:
                try:
                    os.remove(filePath)
                except IsADirectoryError:
                    shutil.rmtree(filePath)
        except Exception as e:
            if self.cfdOk_:
                logger.info("Catch exception in delete: %s", e)
            else:
                pass

    def get_history(self):
        return self.history_


def runTistos(x, state, solver_launcher=None):
    ti = tistos(x, state, solver_launcher=solver_launcher)
    state = ti.state
    ti.pre()
    ti.mesh()
    if not ti.MeshOk_:
        raise RuntimeError(f"Mesh generation failed for {state}")
    logger.info(f"Proxy: Finished Meshing state {state}. Next Step: running cfd")
    ti.run()
    if not ti.cfdOk_:
        reason = ti.history_.get("ReasonOfFailure", "unknown CFD failure")
        raise RuntimeError(f"OpenFOAM failed for {state}: {reason}")
    logger.info(f"Proxy: Finished Running CFD State {state}.")
    fit, fit_extra = ti.evaluate()
    logger.info(f"Proxy: Finished evaluate: {fit}")
    ti.delete()
    history = ti.get_history()
    for key in fit_extra:
        if type(fit_extra[key]) == np.float64:
            # logger.info(f"type of {key}: {type(fit_extra[key])}.")
            fit_extra[key] = float(fit_extra[key])
        # logger.info(f"type of {key}: {type(fit_extra[key])}.")
        elif type(fit_extra[key]) == np.ndarray:
            # logger.info(f"type of {key}: {type(fit_extra[key])}.")
            fit_extra[key] = list(fit_extra[key])
        # logger.info(f"type of {key}: {type(fit_extra[key])}.")
    if type(fit) == np.ndarray:
        fit = list(fit)  # serializable
    elif type(fit) == np.float64:
        fit = float(fit)
    # logger.info(f"type of fit: {type(fit)}.")
    # fit_extra = {}
    return fit, fit_extra, state, history


if __name__ == "__main__":
    ## Geometrieparameter
    x = np.array(
        [
            -0.11438032,
            -0.16330727,
            -0.12347644,
            0.04519614,
            -0.03833768,
            0.01815242,
            1.38688502,
            1.48812174,
            1.43800951,
            0.51168807,
            0.50356657,
            0.50007975,
            -0.05588548,
            -0.09595725,
            -0.00877194,
            0.72367283,
            0.99274612,
            1.12017201,
            0.00703073,
            0.00662532,
            0.00570674,
            0.00818822,
            0.00783633,
            0.00976244,
            0.00885879,
            0.00653766,
            0.00964224,
            0.48951801,
            0.54581857,
            0.54440488,
        ]
    )
    state = "TEST_1"
    runTistos(x, state)
