"""Plot the di-lepton recoil mass (reconstructed Higgs mass) of all samples in one figure.

Usage:
    python plot_recoil.py [<dir with *_recoil.npz>] [output.pdf]
    The directory defaults to $dtDir/<RECO_SUBDIR> (see paths.py).
"""

import sys
from glob import glob
from os import path as osp

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from paths import RECO_SUBDIR, data_dir
from samples import FCCEE, ILC, Sample, parse_sample

PROCESS_LABELS = {
    "e2e2h_inv": r"$ZH \to \mu\mu + H_\mathrm{inv}$",
    "4f_mumununu": r"$\mu\mu\nu\nu$",
}


def label(sample: Sample) -> str:
    return (
        f"{PROCESS_LABELS.get(sample.process, sample.process)}, "
        f"ILD@{sample.collider} {sample.energy} GeV" + ("" if sample.isr else ", no ISR")
    )


def main(in_dir, output):
    files = sorted(glob(osp.join(in_dir, "*_recoil.npz")))
    if not files:
        sys.exit(f"No *_recoil.npz files found in {in_dir}")

    bins = np.linspace(100, 160, 121)
    colors = {
        ("e2e2h_inv", ILC): "C0",
        ("e2e2h_inv", FCCEE): "C1",
        ("4f_mumununu", ILC): "C2",
        ("4f_mumununu", FCCEE): "C3",
    }

    fig, ax = plt.subplots(figsize=(9, 6))
    for f in files:
        sample = parse_sample(f)
        data = np.load(f)
        m = data["m_recoil"][data["has_pair"]]
        ax.hist(
            m,
            bins=bins,
            histtype="step",
            lw=1.5,
            color=colors.get((sample.process, sample.collider)),
            ls="-" if sample.isr else "--",
            label=f"{label(sample)} ({len(m)} ev.)",
        )

    ax.axvline(125.0, color="grey", lw=0.8, ls=":")
    ax.set_xlabel(r"$M_\mathrm{recoil}(\mu\mu)$ [GeV]")
    ax.set_ylabel(f"Events / {bins[1] - bins[0]:.1f} GeV (10k generated)")
    ax.set_title("Reconstructed Higgs mass (SGV fast simulation)")
    ax.set_xlim(bins[0], bins[-1])
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(output)
    fig.savefig(osp.splitext(output)[0] + ".png", dpi=150)
    print(f"Saved {output}")


if __name__ == "__main__":
    in_dir = sys.argv[1] if len(sys.argv) > 1 else str(data_dir() / RECO_SUBDIR)
    output = sys.argv[2] if len(sys.argv) > 2 else osp.join(in_dir, "recoil_mass.pdf")
    main(in_dir, output)
