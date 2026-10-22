"""Run one dtOO geometry operation in a dedicated process."""

import argparse
import os

from dtOOPythonSWIG import (
    baseContainer,
    dtXmlParser,
    labeledVectorHandlingAnalyticFunction,
    labeledVectorHandlingAnalyticGeometry,
    labeledVectorHandlingBoundedVolume,
    labeledVectorHandlingConstValue,
    labeledVectorHandlingDtCase,
    labeledVectorHandlingDtPlugin,
)


class createStatesAndMeshes:
    def CreateStates(self, state):
        xmlName = os.path.join(state + ".xml")
        dtXmlParser.init("tistos_files/machine.xml", xmlName)
        parser = dtXmlParser.reference()
        parser.parse()
        bC = baseContainer()
        cV = labeledVectorHandlingConstValue()
        aF = labeledVectorHandlingAnalyticFunction()
        aG = labeledVectorHandlingAnalyticGeometry()
        bV = labeledVectorHandlingBoundedVolume()
        dC = labeledVectorHandlingDtCase()
        dP = labeledVectorHandlingDtPlugin()
        parser.createConstValue(cV)
        parser.loadStateToConst(state, cV)
        parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
        # dP.get('csv_meanplane').apply()
        dP.get("ru_adjustDomain").apply()
        os.remove(xmlName)
        parser.extract(state, cV, xmlName)

    def CreateMeshes(self, state, caseName, cfdMesh=True):
        xmlName = os.path.join(state + ".xml")
        dtXmlParser.init("tistos_files/machine.xml", xmlName)
        parser = dtXmlParser.reference()
        parser.parse()
        bC = baseContainer()
        cV = labeledVectorHandlingConstValue()
        aF = labeledVectorHandlingAnalyticFunction()
        aG = labeledVectorHandlingAnalyticGeometry()
        bV = labeledVectorHandlingBoundedVolume()
        dC = labeledVectorHandlingDtCase()
        dP = labeledVectorHandlingDtPlugin()
        parser.createConstValue(cV)
        parser.loadStateToConst(state, cV)
        parser.destroyAndCreate(bC, cV, aF, aG, bV, dC, dP)
        if cfdMesh:
            # make cfd mesh
            for i in ["_n"]:
                dC.get(caseName + i).runCurrentState()


def main(argv: list[str] | None = None) -> int:
    """Dispatch an operation using XML paths relative to the child cwd."""
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("state", "mesh"))
    parser.add_argument("state")
    args = parser.parse_args(argv)
    implementation = createStatesAndMeshes()
    if args.operation == "state":
        implementation.CreateStates(args.state)
    else:
        implementation.CreateMeshes(args.state, "tistos_ru_of")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
