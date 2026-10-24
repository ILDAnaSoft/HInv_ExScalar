"""Compute the di-lepton recoil mass (= reconstructed Higgs mass for H -> invisible)
from the output of steering_llrecoil.py and store it as .npz next to the input.

The initial state is taken as the sum of the two incoming beam particles
(generator status 4) in MCParticlesSkimmed. These carry the nominal beam energy
and any crossing-angle boost applied by SGV, so the recoil is computed in the
correct frame for both ILC and FCC-ee files.

Usage (key4hep sourced):
    python extract_recoil.py [<reco.slcio> ...]
    Without arguments, all .slcio files in $dtDir/<RECO_SUBDIR> (see paths.py) are processed.
"""

import sys
import numpy as np
from pyLCIO import IOIMPL

from paths import RECO_SUBDIR, data_dir


def four_vector(p):
    mom = p.getMomentum()
    return np.array([p.getEnergy(), mom[0], mom[1], mom[2]])


def minkowski_mass(v):
    m2 = v[0] ** 2 - v[1] ** 2 - v[2] ** 2 - v[3] ** 2
    return np.sign(m2) * np.sqrt(np.abs(m2))


def initial_state(mc_col):
    beams = [
        four_vector(mc_col.getElementAt(i))
        for i in range(mc_col.getNumberOfElements())
        if mc_col.getElementAt(i).getGeneratorStatus() == 4
    ]
    assert len(beams) == 2, f"expected 2 incoming beams, found {len(beams)}"
    return beams[0] + beams[1]


def process_file(path):
    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(path)

    m_recoil, m_ll, has_pair = [], [], []
    cross_section = np.nan

    for event in reader:
        if np.isnan(cross_section):
            cross_section = event.getParameters().getFloatVal("crossSection")

        p_init = initial_state(event.getCollection("MCParticlesSkimmed"))

        pair = event.getCollection("LeptonPair")
        if pair.getNumberOfElements() == 2:
            p_ll = four_vector(pair.getElementAt(0)) + four_vector(pair.getElementAt(1))
            m_recoil.append(minkowski_mass(p_init - p_ll))
            m_ll.append(minkowski_mass(p_ll))
            has_pair.append(True)
        else:
            m_recoil.append(np.nan)
            m_ll.append(np.nan)
            has_pair.append(False)

    reader.close()

    out = path.rsplit(".", 1)[0] + "_recoil.npz"
    np.savez(
        out,
        m_recoil=np.array(m_recoil),
        m_ll=np.array(m_ll),
        has_pair=np.array(has_pair),
        cross_section=cross_section,
    )
    print(f"{path}: {sum(has_pair)}/{len(has_pair)} events with lepton pair -> {out}")


if __name__ == "__main__":
    files = sys.argv[1:] or sorted(str(f) for f in (data_dir() / RECO_SUBDIR).glob("*.slcio"))
    if not files:
        sys.exit("No input files given or found")
    for f in files:
        process_file(f)
