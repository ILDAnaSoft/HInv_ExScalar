"""Machine- and user-independent paths, derived from environment variables.

Required:
    $codeDir : directory containing the code checkouts (SGV_install, ZHH, ...)
    $dtDir   : data directory (generator files, SGV and reco outputs)
Optional:
    $SGV_DIR : SGV installation, defaults to $codeDir/SGV_install/sgv

The variables are read lazily, so scripts only fail if a path is actually needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ENV_DESCRIPTIONS = {
    "codeDir": "the directory containing the code checkouts (SGV_install, ZHH, ...)",
    "dtDir": "the data directory (generator files, SGV and reco outputs)",
}

# default data sub-directories below $dtDir; each production run gets its own dated
# sub-directory, so outputs of different inputs/runs are never mixed
RUN = "2026-10-27"
WHIZARD_SUBDIR = f"2026-10-whizard/{RUN}"
SGV_SUBDIR = f"2026-10-sgv/{RUN}"
RECO_SUBDIR = f"2026-10-reco/{RUN}"


def env_dir(name: str) -> Path:
    """Returns the directory stored in env var `name`; exits with a clear message if unusable."""
    value = os.environ.get(name)
    if not value:
        sys.exit(
            f"Error: environment variable ${name} is not set.\n"
            f"Set it to {ENV_DESCRIPTIONS.get(name, 'the corresponding directory')}, e.g.\n"
            f"    export {name}=/path/to/dir"
        )
    path = Path(value).expanduser()
    if not path.is_dir():
        sys.exit(f"Error: ${name}={value} is not an existing directory.")
    return path


def code_dir() -> Path:
    return env_dir("codeDir")


def data_dir() -> Path:
    return env_dir("dtDir")


def sgv_dir() -> Path:
    return (
        Path(os.environ["SGV_DIR"])
        if os.environ.get("SGV_DIR")
        else code_dir() / "SGV_install/sgv"
    )


def lepton_pairing_lib() -> Path:
    return code_dir() / "ZHH/source/LeptonPairing/lib/libLeptonPairing.so"
