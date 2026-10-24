"""Sample bookkeeping: parse sample file names and provide collider-dependent settings.

File names follow the WHIZARD/ILD convention, e.g.
    E240-FCCee_PB_noISR.Pe2e2h_inv.Gwhizard-3_1_5.eU.pU.I403001.0.slcio
    E250-SetA.P4f_mumununu.Gwhizard-3_1_5.eL.pR.I403002.0_recoil.npz
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from paths import sgv_dir

REPO_DIR = Path(__file__).resolve().parent.parent

ILC = "ILC"
FCCEE = "FCC-ee"


@dataclass(frozen=True)
class Sample:
    energy: int  # nominal centre-of-mass energy [GeV]
    collider: str  # ILC or FCCEE
    isr: bool
    process: str  # e.g. e2e2h_inv


@dataclass(frozen=True)
class ColliderSettings:
    cms_energy: float  # [GeV]
    crossing_angle: float  # half crossing angle [rad], applied by SGV to head-on events
    sgv_geometry: Path
    detector_model: str  # full-sim model for the Gaudi steering (and LCIO header)


def parse_sample(path: str | os.PathLike) -> Sample:
    tokens = Path(path).name.split(".")
    if len(tokens) < 2 or not tokens[1].startswith("P"):
        raise ValueError(f"Cannot parse sample name: {path}")

    setup, process = tokens[0], tokens[1][1:]
    energy, machine = setup.split("-", 1)
    return Sample(
        energy=int(energy.lstrip("E")),
        collider=FCCEE if machine.startswith("FCCee") else ILC,
        isr=not machine.endswith("_noISR"),
        process=process,
    )


def collider_settings(sample: Sample, ild_fcc_version: int = 1) -> ColliderSettings:
    """ILD@FCC uses the given ILD_FCCee version (1 or 2), ILD@ILC uses ILD_l5_o1_v02."""
    if sample.collider == FCCEE:
        settings = ColliderSettings(
            cms_energy=float(sample.energy),
            crossing_angle=0.015,  # 30 mrad full crossing angle
            sgv_geometry=REPO_DIR
            / f"sgv_geometries/sgv_geo_fullsim_ildfcc_v{ild_fcc_version}.inp",
            detector_model=f"ILD_FCCee_v{ild_fcc_version:02d}",
        )
    else:
        settings = ColliderSettings(
            cms_energy=float(sample.energy),
            crossing_angle=0.007,  # 14 mrad full crossing angle
            sgv_geometry=sgv_dir() / "tests/sgv_geo.inp",
            detector_model="ILD_l5_o1_v02",
        )

    if not settings.sgv_geometry.is_file():
        raise FileNotFoundError(f"SGV geometry not found: {settings.sgv_geometry}")
    return settings
