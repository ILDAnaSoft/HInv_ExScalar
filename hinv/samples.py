"""Sample bookkeeping: parse sample file names and provide collider-dependent settings.

File names follow the WHIZARD/ILD convention, e.g.
    E240-FCCee_PB_noISR.Pe2e2h_inv.Gwhizard-3_1_5.eU.pU.I403001.0.slcio
    E250-SetA.P4f_mumununu.Gwhizard-3_1_5.eL.pR.I403002.0_obs.npz
    E250-SetA.P2f_mumu.eL.pR.I403003  (sample directory of the WHIZARD production)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from hinv.paths import sgv_dir

REPO_DIR = Path(__file__).resolve().parent.parent

ILC = "ILC"
FCCEE = "FCC-ee"


@dataclass(frozen=True)
class Sample:
    energy: int  # nominal centre-of-mass energy [GeV]
    collider: str  # ILC or FCCEE
    isr: bool
    process: str  # e.g. e2e2h_inv
    polarisation: str | None = None  # eL.pR, eR.pL or eU.pU (unpolarised)
    process_id: int | None = None
    file_index: int | None = None

    @property
    def key(self) -> tuple:
        """Identifies the sample independent of the file, e.g. to group its files."""
        return (self.collider, self.energy, self.isr, self.process, self.polarisation)


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

    polarisation = process_id = file_index = None
    for i, token in enumerate(tokens[2:], start=2):
        following = tokens[i + 1] if i + 1 < len(tokens) else ""
        if token in ("eL", "eR", "eU") and following in ("pL", "pR", "pU"):
            polarisation = f"{token}.{following}"
        elif token.startswith("I") and token[1:].isdigit():
            process_id = int(token[1:])
            # the file index follows the process ID, possibly with a suffix (0_obs, ...)
            index = following.split("_")[0]
            file_index = int(index) if index.isdigit() else None

    return Sample(
        energy=int(energy.lstrip("E")),
        collider=FCCEE if machine.startswith("FCCee") else ILC,
        isr=not machine.endswith("_noISR"),
        process=process,
        polarisation=polarisation,
        process_id=process_id,
        file_index=file_index,
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


# --- run plans and polarisation weights -------------------------------------------------------
# TODO: check against the official run plans before showing results
#   ILC250 "H20": 2 ab^-1, 45 % each (-0.8, +0.3) and (+0.8, -0.3), 5 % each (-,-), (+,+)
#   FCC-ee: 10.8 ab^-1 at 240 GeV
# The (-,-) and (+,+) runs are omitted: there are no LL/RR samples, and ZH and mumununu
# (s-channel, t-channel nu exchange) vanish there; for eemumu (t-channel photon) they would not.


@dataclass(frozen=True)
class Run:
    name: str
    collider: str
    energy: int
    luminosity: float  # integrated luminosity [fb^-1]
    pol_electron: float = 0.0  # P(e-), -0.8 = 80 % left-handed
    pol_positron: float = 0.0  # P(e+)

    def helicity_fraction(self, polarisation: str) -> float:
        """Fraction of this run's luminosity in a fully polarised sample's helicity state."""
        if polarisation == "eU.pU":
            if self.pol_electron or self.pol_positron:
                raise ValueError(f"unpolarised sample used for polarised run {self.name}")
            return 1.0
        sign_e = -1 if polarisation.startswith("eL") else 1
        sign_p = -1 if polarisation.endswith("pL") else 1
        return (1 + sign_e * self.pol_electron) * (1 + sign_p * self.pol_positron) / 4

    def polarisations(self) -> tuple[str, ...]:
        if self.pol_electron or self.pol_positron:
            return ("eL.pR", "eR.pL")
        return ("eU.pU",)


RUNS = {
    "ILC250_LR": Run("ILC 250, P(e-,e+) = (-0.8, +0.3)", ILC, 250, 900.0, -0.8, 0.3),
    "ILC250_RL": Run("ILC 250, P(e-,e+) = (+0.8, -0.3)", ILC, 250, 900.0, 0.8, -0.3),
    "FCCee240": Run("FCC-ee 240", FCCEE, 240, 10800.0),
}
