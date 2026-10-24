"""Plot the di-lepton recoil mass (reconstructed Higgs mass) of all samples in one figure.

Usage:
    python plot_recoil.py <dir with *_recoil.npz> [output.pdf]
"""

import sys
from glob import glob
from os import path as osp

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROCESS_LABELS = {
    "e2e2h_inv": r"$ZH \to \mu\mu + H_\mathrm{inv}$",
    "4f_mumununu": r"$\mu\mu\nu\nu$",
}


def describe(fname):
    """Parse e.g. E240-FCCee_PB_noISR.Pe2e2h_inv.Gwhizard-3_1_5.eU.pU.I403001.0_recoil.npz"""
    tokens = osp.basename(fname).split(".")
    setup, process = tokens[0], tokens[1][1:]
    energy, machine = setup.split("-", 1)
    collider = "FCC-ee" if machine.startswith("FCCee") else "ILC"
    isr = not machine.endswith("_noISR")
    return dict(
        process=process,
        collider=collider,
        isr=isr,
        label=f"{PROCESS_LABELS.get(process, process)}, ILD@{collider} {energy[1:]} GeV"
        + ("" if isr else ", no ISR"),
    )


def main(in_dir, output):
    files = sorted(glob(osp.join(in_dir, "*_recoil.npz")))
    if not files:
        sys.exit(f"No *_recoil.npz files found in {in_dir}")

    bins = np.linspace(100, 160, 121)
    colors = {
        ("e2e2h_inv", "ILC"): "C0",
        ("e2e2h_inv", "FCC-ee"): "C1",
        ("4f_mumununu", "ILC"): "C2",
        ("4f_mumununu", "FCC-ee"): "C3",
    }

    fig, ax = plt.subplots(figsize=(9, 6))
    for f in files:
        d = describe(f)
        data = np.load(f)
        m = data["m_recoil"][data["has_pair"]]
        ax.hist(
            m,
            bins=bins,
            histtype="step",
            lw=1.5,
            color=colors.get((d["process"], d["collider"])),
            ls="-" if d["isr"] else "--",
            label=f"{d['label']} ({len(m)} ev.)",
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
    in_dir = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else osp.join(in_dir, "recoil_mass.pdf")
    main(in_dir, output)
