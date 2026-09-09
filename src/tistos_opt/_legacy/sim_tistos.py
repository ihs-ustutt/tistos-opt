import subprocess
import xml.etree.ElementTree as ET
import os
import shutil
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
    def __init__(self, x, state):
        self.state = state
        self.history_ = {}
        self.history_["DateOfBirth"] = time.ctime()
        self.x = x
        # self.mainDir = os.getcwd()
        self.stateNumber = int(self.state.split("_")[-1])
        self.caseName = "tistos_ru_of"
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

    def evaluate(self, *, laminar_end_time=100, end_time=500):
        try:
            logger.info(f"POST PROCESSING {self.state}")
            aProb = tistosRunner(
                case=self.caseName,
                prefix=self.state.split("_")[0],
                stateNumber=self.stateNumber,
                coeff=self.x,
                laminar_end_time=laminar_end_time,
                end_time=end_time,
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
            logger.exception("Evaluation Exception")
            raise
        return fit, fit_extra

    def delete(self):
        cleanupTistos(
            self.state,
            case=self.caseName,
        )

    def get_history(self):
        return self.history_


def cleanupTistos(state, case="tistos_ru_of", log_errors=True):
    """Delete generated files for one state while retaining staged assets."""
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
        if log_errors:
            logger.info("Catch exception in delete: %s", e)
