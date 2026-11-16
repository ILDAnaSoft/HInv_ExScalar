"""Run plans: which collider run a sample is weighted to.

The energy, luminosity and polarisation of a run are defined only in its cutflow steering file in
hinv/configs, as the cutflow tool cannot read them from anywhere else. Everything else, e.g.
hinv.ana.dataset, reads them from there.

TODO: check against the official run plans before showing results
  ILC250 "H20": 2 ab^-1, 45 % each (-0.8, +0.3) and (+0.8, -0.3), 5 % each (-,-), (+,+)
  FCC-ee: 10.8 ab^-1 at 240 GeV
The (-,-) and (+,+) runs are omitted: there are no LL/RR samples, and ZH and mumununu
(s-channel, t-channel nu exchange) vanish there; for eemumu (t-channel photon) they would not.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from hinv.samples import FCCEE, ILC

CONFIG_DIR = Path(__file__).resolve().parent / "configs"


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


def load_run(collider: str, steering: str) -> Run:
    """Creates a Run from the settings of a cutflow steering file."""
    steer = yaml.safe_load((CONFIG_DIR / steering).read_text())
    pol_electron, pol_positron = steer["beam_polarization"]
    energy = steer["sqrt_s"]

    name = f"{collider} {energy}"
    if pol_electron or pol_positron:
        name += f", P(e-,e+) = ({pol_electron:+.1f}, {pol_positron:+.1f})"
    return Run(name, collider, energy, steer["luminosity"] * 1000.0, pol_electron, pol_positron)


RUNS = {
    "ILC250_LR": load_run(ILC, "e2e2h_inv_ilc250_lr.yaml"),
    "ILC250_RL": load_run(ILC, "e2e2h_inv_ilc250_rl.yaml"),
    "FCCee240": load_run(FCCEE, "e2e2h_inv_fcc240.yaml"),
}
