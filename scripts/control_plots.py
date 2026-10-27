"""Control plots of the selection observables, weighted to the luminosity of each run.

Backgrounds are stacked, the signal (BR(H->inv) = 100 %) is drawn as a line on top. Only events
with a mu+mu- pair are shown (preselection of the muon channel). Also prints the expected yields.

Usage:
    python control_plots.py [--runs ILC250_LR ILC250_RL FCCee240] [--out DIR]
    Plots default to $dtDir/<RECO_SUBDIR>/plots.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from dataset import PROCESSES, SIGNAL, load_run
from paths import RECO_SUBDIR, data_dir
from samples import RUNS

INK = "#1b1b1a"
MUTED = "#6b6a63"
GRID = "#e4e3de"

# observable -> (axis label, bins)
PANELS = {
    "m_ll": (r"$m_{\mu\mu}$ [GeV]", np.linspace(0, 250, 51)),
    "m_recoil": (r"$M_\mathrm{recoil}$ [GeV]", np.linspace(0, 250, 51)),
    "pt_ll": (r"$p_{T,\mu\mu}$ [GeV]", np.linspace(0, 120, 49)),
    "cos_ll": (r"$\cos\theta_{\mu\mu}$", np.linspace(-1, 1, 41)),
    "acoplanarity": (
        r"acoplanarity $\pi - |\Delta\phi_{\mu\mu}|$ [rad]",
        np.linspace(0, np.pi, 41),
    ),
    "cos_miss": (r"$|\cos\theta_\mathrm{miss}|$", np.linspace(0, 1, 41)),
    "pt_miss": (r"$p_{T,\mathrm{miss}}$ [GeV]", np.linspace(0, 120, 49)),
    "e_rest": (r"$E$ of PFOs without the pair [GeV]", np.linspace(0, 150, 51)),
    "n_isolep": ("number of isolated leptons", np.arange(-0.5, 7.5, 1)),
}


def preselection(arrays: dict[str, np.ndarray]) -> np.ndarray:
    return arrays["pair_type"] == 13


def style_axes(ax):
    ax.set_yscale("log")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.xaxis.label.set_color(INK)
    ax.yaxis.label.set_color(INK)


def plot_run(run_key: str, data: dict, out_dir: Path):
    run = RUNS[run_key]
    backgrounds = [p for p in PROCESSES if p != SIGNAL and p in data]
    selected = {p: preselection(a) for p, a in data.items()}

    fig, axes = plt.subplots(3, 3, figsize=(13, 10.5))
    for ax, (obs, (xlabel, bins)) in zip(axes.flat, PANELS.items()):
        values = [data[p][obs][selected[p]] for p in backgrounds]
        weights = [data[p]["weight"][selected[p]] for p in backgrounds]
        ax.hist(
            values,
            bins=bins,
            weights=weights,
            stacked=True,
            histtype="stepfilled",
            color=[PROCESSES[p].color for p in backgrounds],
            edgecolor="white",
            linewidth=0.6,
            label=[PROCESSES[p].label for p in backgrounds],
        )
        if SIGNAL in data:
            ax.hist(
                data[SIGNAL][obs][selected[SIGNAL]],
                bins=bins,
                weights=data[SIGNAL]["weight"][selected[SIGNAL]],
                histtype="step",
                color=PROCESSES[SIGNAL].color,
                linewidth=2,
                label=PROCESSES[SIGNAL].label + " (BR = 100 %)",
            )
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_ylabel("events / bin", fontsize=9)
        ax.set_xlim(bins[0], bins[-1])
        ax.set_ylim(bottom=0.5)
        style_axes(ax)

    handles, labels = axes.flat[0].get_legend_handles_labels()
    order = [
        labels.index(PROCESSES[p].label + " (BR = 100 %)")
        if p == SIGNAL
        else labels.index(PROCESSES[p].label)
        for p in PROCESSES
        if p in data
    ]
    fig.legend(
        [handles[i] for i in order],
        [labels[i] for i in order],
        loc="upper center",
        ncol=len(order),
        frameon=False,
        fontsize=10,
        bbox_to_anchor=(0.5, 0.995),
    )
    fig.suptitle(
        f"{run.name}, {run.luminosity / 1000:g} ab$^{{-1}}$ · SGV · preselection: $\\mu^+\\mu^-$ pair",
        y=0.965,
        fontsize=11,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out = out_dir / f"control_{run_key}"
    fig.savefig(f"{out}.pdf")
    fig.savefig(f"{out}.png", dpi=130)
    plt.close(fig)
    return f"{out}.png"


def yield_table(run_key: str, data: dict):
    run = RUNS[run_key]
    print(f"\n{run.name}, {run.luminosity / 1000:g} ab^-1")
    print(
        f"  {'process':16s} {'generated':>10s} {'all events':>12s} {'mu mu pair':>12s} {'eff.':>7s}"
    )
    for p, a in data.items():
        sel = preselection(a)
        total, passed = a["weight"].sum(), a["weight"][sel].sum()
        print(
            f"  {p:16s} {len(a['weight']):10d} {total:12.4g} {passed:12.4g} {passed / total:7.1%}"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", nargs="+", default=list(RUNS), choices=list(RUNS))
    parser.add_argument("--out", type=Path, help=f"Default: $dtDir/{RECO_SUBDIR}/plots")
    args = parser.parse_args()

    out_dir = args.out or data_dir() / RECO_SUBDIR / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    for run_key in args.runs:
        data = load_run(run_key)
        yield_table(run_key, data)
        print(f"  -> {plot_run(run_key, data, out_dir)}")


if __name__ == "__main__":
    main()
