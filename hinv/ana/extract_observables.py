"""Extract the per-event observables of the ZH -> ll + X recoil analysis from the output of
steering/llrecoil.py and store them as <file>_obs.npz next to each input file.

The initial state is the sum of the two incoming beam particles (generator status 4) in
MCParticlesSkimmed: nominal beam energy plus the crossing-angle boost applied by SGV. The
recoil mass is Lorentz invariant; all angles and transverse momenta are computed in the rest
frame of this initial state, so that the crossing angle does not fake transverse momentum.

Usage (key4hep sourced):
    python -m hinv.ana.extract_observables [--jobs N] [<reco.slcio> ...]
    Without files, all .slcio files in $dtDir/<RECO_SUBDIR> (see paths.py) are processed.
"""

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import numpy as np

from hinv.paths import RECO_SUBDIR, data_dir

# per-event observables; NaN where undefined (e.g. no lepton pair)
OBSERVABLES = {
    "pair_type": "PDG type of the paired leptons (0: no pair)",
    "m_ll": "di-lepton mass after photon recovery [GeV]",
    "m_recoil": "recoil mass against the lepton pair [GeV]",
    "pt_ll": "transverse momentum of the lepton pair [GeV]",
    "p_ll": "momentum of the lepton pair [GeV]",
    "cos_ll": "cos(polar angle) of the lepton pair",
    "acoplanarity": "pi - |delta phi| between the two leptons [rad]",
    "cos_lep_max": "largest |cos(polar angle)| of the two leptons",
    "pt_miss": "missing transverse momentum (all visible PFOs) [GeV]",
    "cos_miss": "|cos(polar angle)| of the missing momentum",
    "e_rest": "energy of all PFOs except the lepton pair [GeV]",
    "n_rest": "number of PFOs except the lepton pair",
    "n_isolep": "number of isolated leptons (muons + electrons)",
}


def four_vector(p):
    mom = p.getMomentum()
    return np.array([p.getEnergy(), mom[0], mom[1], mom[2]])


def mass(v):
    m2 = v[0] ** 2 - v[1:] @ v[1:]
    return np.sign(m2) * np.sqrt(np.abs(m2))


def boost_to_rest_frame(v, frame):
    """Boosts four-vector v into the rest frame of four-vector frame."""
    beta = frame[1:] / frame[0]
    b2 = beta @ beta
    if b2 == 0:
        return v
    gamma = 1 / np.sqrt(1 - b2)
    bp = beta @ v[1:]
    e = gamma * (v[0] - bp)
    p = v[1:] + ((gamma - 1) * bp / b2 - gamma * v[0]) * beta
    return np.array([e, *p])


def pt(v):
    return np.hypot(v[1], v[2])


def cos_theta(v):
    p = np.linalg.norm(v[1:])
    return v[3] / p if p > 0 else np.nan


def initial_state(mc_col):
    beams = [
        four_vector(mc_col.getElementAt(i))
        for i in range(mc_col.getNumberOfElements())
        if mc_col.getElementAt(i).getGeneratorStatus() == 4
    ]
    assert len(beams) == 2, f"expected 2 incoming beams, found {len(beams)}"
    return beams[0] + beams[1]


def n_elements(event, name):
    try:
        return event.getCollection(name).getNumberOfElements()
    except Exception:
        return 0


def event_observables(event):
    obs = dict.fromkeys(OBSERVABLES, np.nan)
    p_init = initial_state(event.getCollection("MCParticlesSkimmed"))

    rest = event.getCollection("PandoraPFOsWithoutLepPair")
    rest_vecs = [
        boost_to_rest_frame(four_vector(rest.getElementAt(i)), p_init)
        for i in range(rest.getNumberOfElements())
    ]
    p_rest = np.sum(rest_vecs, axis=0) if rest_vecs else np.zeros(4)
    obs["e_rest"] = p_rest[0]
    obs["n_rest"] = len(rest_vecs)
    obs["n_isolep"] = n_elements(event, "ISOMuons") + n_elements(event, "ISOElectrons")

    pair = event.getCollection("LeptonPair")
    if pair.getNumberOfElements() != 2:
        obs["pair_type"] = 0
        return obs

    obs["pair_type"] = abs(pair.getParameters().getIntVal("PairedType"))
    leptons_lab = [four_vector(pair.getElementAt(i)) for i in range(2)]
    p_ll_lab = leptons_lab[0] + leptons_lab[1]
    obs["m_ll"] = mass(p_ll_lab)
    obs["m_recoil"] = mass(p_init - p_ll_lab)

    l1, l2 = (boost_to_rest_frame(v, p_init) for v in leptons_lab)
    p_ll = l1 + l2
    obs["pt_ll"] = pt(p_ll)
    obs["p_ll"] = np.linalg.norm(p_ll[1:])
    obs["cos_ll"] = cos_theta(p_ll)
    dphi = abs(np.arctan2(l1[2], l1[1]) - np.arctan2(l2[2], l2[1]))
    obs["acoplanarity"] = np.pi - min(dphi, 2 * np.pi - dphi)
    obs["cos_lep_max"] = max(abs(cos_theta(l1)), abs(cos_theta(l2)))

    p_miss = -(p_ll[1:] + p_rest[1:])  # initial-state momentum is zero in its rest frame
    obs["pt_miss"] = np.hypot(p_miss[0], p_miss[1])
    obs["cos_miss"] = abs(p_miss[2] / np.linalg.norm(p_miss)) if p_miss.any() else np.nan
    return obs


def process_file(path):
    from pyLCIO import IOIMPL  # imported per worker process

    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(path)
    columns = {name: [] for name in OBSERVABLES}
    cross_section = cross_section_error = np.nan

    for event in reader:
        if np.isnan(cross_section):
            params = event.getParameters()
            cross_section = params.getFloatVal("crossSection")
            cross_section_error = params.getFloatVal("crossSectionError")
        for name, value in event_observables(event).items():
            columns[name].append(value)
    reader.close()

    out = path.rsplit(".", 1)[0] + "_obs.npz"
    arrays = {name: np.array(values, dtype=float) for name, values in columns.items()}
    np.savez(
        out,
        **arrays,
        cross_section=cross_section,
        cross_section_error=cross_section_error,
        n_events=len(arrays["m_ll"]),
    )
    n_pairs = int(np.sum(arrays["pair_type"] > 0))
    return f"{path.rsplit('/', 1)[-1]}: {n_pairs}/{len(arrays['m_ll'])} events with lepton pair"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="*", help=f"Default: $dtDir/{RECO_SUBDIR}/*.slcio")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel processes (default: 8)")
    args = parser.parse_args()

    files = args.files or sorted(str(f) for f in (data_dir() / RECO_SUBDIR).glob("*.slcio"))
    if not files:
        sys.exit("No input files given or found")

    # spawn: fresh interpreters, so ROOT/pyLCIO are initialised per process
    with ProcessPoolExecutor(max_workers=args.jobs, mp_context=get_context("spawn")) as pool:
        for message in pool.map(process_file, files):
            print(message)


if __name__ == "__main__":
    main()
