"""Prepare and clean TiStoS files using the bundled dtOO inputs."""

import logging
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path

from tistos_opt.case import PARAMETERS

logger = logging.getLogger(__name__)


def prepare_case(
    work_dir: Path, state: str, parameters: Mapping[str, float]
) -> dict[str, str]:
    """Write named inputs, mesh the case, and return preparation history."""
    work_dir = work_dir.resolve()
    history = {"DateOfBirth": time.ctime()}
    template = ET.parse(work_dir / "tistos_files" / "templateState.xml")
    state_element = template.find("state")
    if state_element is None:
        raise ValueError("TiStoS template has no state element")
    state_element.set("label", state)
    for parameter in PARAMETERS:
        element = state_element.find(
            f"constValue[@label='{parameter.legacy_label}']"
        )
        if element is None:
            raise ValueError(
                f"missing template label: {parameter.legacy_label}"
            )
        element.set("value", str(float(parameters[parameter.name])))
    template.write(work_dir / f"{state}.xml")

    # Separate processes preserve dtOO parser isolation. Only the children use
    # the working directory required by relative paths in the XML inputs.
    for operation in ("state", "mesh"):
        logger.info("Generating %s for %s", operation, state)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "tistos_opt._legacy.tistos_files.createStatesAndMeshes",
                operation,
                state,
            ],
            cwd=work_dir,
            timeout=300,
            check=True,
        )
    case_dir = work_dir / f"tistos_ru_of_n_{state}"
    if not all(
        (case_dir / name).is_dir() for name in ("system", "constant", "0")
    ):
        raise RuntimeError(f"CFD mesh not written for state: {state}")
    history["DateOfCreation"] = time.ctime()
    return history


def cleanup_case(work_dir: Path, state: str) -> None:
    """Delete generated files after the result is saved, retaining inputs."""
    try:
        paths = [*work_dir.glob(f"{state}.*"), *work_dir.glob(f"{state}_*")]
        paths.append(work_dir / f"tistos_ru_of_n_{state}")
        for path in paths:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    except OSError:
        logger.exception("Could not clean generated files for %s", state)
