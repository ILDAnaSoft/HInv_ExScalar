"""Load the extracted observables (*_obs.npz) of a run and attach event weights.

Each event of a sample gets the weight
    w = sigma * L * f_hel / N_generated
with the WHIZARD cross section sigma, the run's luminosity L, the fraction f_hel of the run's
luminosity in the sample's helicity state (see samples.Run), and the number of generated events
of the sample, summed over all its files (events without a lepton pair included).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from extract_observables import OBSERVABLES
from paths import RECO_SUBDIR, data_dir
from samples import RUNS, parse_sample

SIGNAL = "e2e2h_inv"


@dataclass(frozen=True)
class Process:
    label: str
    color: str  # categorical slot, fixed per process (dataviz reference palette)


# fixed order: signal first, then backgrounds in stacking order
PROCESSES = {
    "e2e2h_inv": Process(r"ZH $\to \mu\mu$ + inv", "#1b1b1a"),
    "4f_mumununu": Process(r"$\mu\mu\nu\nu$ (ZZ, WW)", "#2a78d6"),
    "2f_mumu": Process(r"$\mu\mu(\gamma)$", "#eb6834"),
    "4f_eemumu": Process(r"$ee\mu\mu$", "#1baf7a"),
}


def load_run(run_key: str, obs_dir: Path | None = None) -> dict[str, dict[str, np.ndarray]]:
    """Returns {process: {observable: array, ..., "weight": array}} for one run of samples.RUNS."""
    run = RUNS[run_key]
    obs_dir = obs_dir or data_dir() / RECO_SUBDIR

    files = defaultdict(list)  # (process, polarisation) -> files
    for f in sorted(obs_dir.glob("*_obs.npz")):
        s = parse_sample(f)
        if (s.collider, s.energy, s.isr) == (run.collider, run.energy, True) and (
            s.polarisation in run.polarisations()
        ):
            files[(s.process, s.polarisation)].append(f)
    if not files:
        raise FileNotFoundError(f"No observables for {run.name} in {obs_dir}")

    parts = defaultdict(list)
    for (process, polarisation), paths in files.items():
        data = [np.load(p) for p in paths]
        xsecs = {float(d["cross_section"]) for d in data}
        if len(xsecs) != 1:
            raise ValueError(f"{process} {polarisation}: files differ in cross section {xsecs}")
        n_generated = sum(int(d["n_events"]) for d in data)
        weight = xsecs.pop() * run.luminosity * run.helicity_fraction(polarisation) / n_generated

        arrays = {k: np.concatenate([d[k] for d in data]) for k in OBSERVABLES}
        arrays["weight"] = np.full(n_generated, weight)
        parts[process].append(arrays)

    for process in PROCESSES:
        found = {pol for (proc, pol) in files if proc == process}
        missing = set(run.polarisations()) - found
        if missing:
            print(f"Warning: {run.name}: no {process} sample for {sorted(missing)}")

    return {
        process: {k: np.concatenate([p[k] for p in parts[process]]) for k in parts[process][0]}
        for process in PROCESSES
        if process in parts
    }
