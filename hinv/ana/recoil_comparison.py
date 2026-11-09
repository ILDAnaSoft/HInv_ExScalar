"""Compare the di-muon mass and the recoil mass of the ZH -> mu mu + inv signal at ILC and FCC-ee.

The WHIZARD record allows to switch on the effects that shape the recoil mass one at a time:
    generator status 4: nominal beams (incl. the crossing-angle boost)
    generator status 2: e+e- after the beam spectrum (circe2: beam energy spread, beamstrahlung)
    generator status 3: e+e- after ISR, entering the hard process
The recoil mass is computed against the hard-process muons (before FSR) or the final-state muons
(after FSR), and for the reconstructed lepton pair (detector). Analysis-like recoil masses always
use the nominal beams, as in data.

Usage (key4hep sourced for the extraction):
    python -m hinv.ana.recoil_comparison [--ilc-polarisation eL.pR] [--out DIR] [--jobs N]
    Reads the signal files in $dtDir/<RECO_SUBDIR>, caches the masses as <file>_recoil.npz there,
    and writes the plots to $dtDir/<RECO_SUBDIR>/plots.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from hinv.ana.dataset import SIGNAL
from hinv.paths import RECO_SUBDIR, data_dir
from hinv.samples import FCCEE, ILC, parse_sample

M_Z = 91.1879  # GeV, PDG 2026
M_H = 125.0  # GeV, as generated

INK = "#1b1b1a"
MUTED = "#6b6a63"
GRID = "#e4e3de"
COLLIDER_COLORS = {ILC: "#eb6834", FCCEE: "#2a78d6"}
COLLIDER_LABELS = {ILC: "ILD@ILC 250", FCCEE: "ILD@FCC-ee 240"}

# recoil mass levels: name -> (label, initial state, muons)
LEVELS = {
    "hard": ("hard process", "after_isr", "hard"),
    "isr": ("+ ISR", "after_spectrum", "hard"),
    "spectrum": ("+ beam spectrum", "nominal", "hard"),
    "fsr": ("+ FSR", "nominal", "final"),
    "reco": ("+ detector (SGV)", "nominal", "reco"),
}


def four_vector(p) -> np.ndarray:
    m = p.getMomentum()
    return np.array([p.getEnergy(), m[0], m[1], m[2]])


def mass(v: np.ndarray) -> float:
    m2 = v[0] ** 2 - v[1:] @ v[1:]
    return float(np.sign(m2) * np.sqrt(abs(m2)))


def event_masses(event) -> dict[str, float] | None:
    """Recoil masses at all levels and the di-muon masses; None without a reconstructed mu pair."""
    pair = event.getCollection("LeptonPair")
    if pair.getNumberOfElements() != 2 or abs(pair.getParameters().getIntVal("PairedType")) != 13:
        return None

    mc = event.getCollection("MCParticlesSkimmed")
    particles = [mc.getElementAt(i) for i in range(mc.getNumberOfElements())]
    electrons = {
        status: sum(
            four_vector(p)
            for p in particles
            if p.getGeneratorStatus() == status and abs(p.getPDG()) == 11
        )
        for status in (4, 2, 3)
    }
    initial = {"nominal": electrons[4], "after_spectrum": electrons[2], "after_isr": electrons[3]}

    # PYTHIA keeps each FSR step as another status-2 copy; the hard-process muons are the first
    # copies, whose parents are the status-3 e+e-
    hard = [
        p
        for p in particles
        if p.getGeneratorStatus() == 2
        and abs(p.getPDG()) == 13
        and any(p.getParents()[i].getGeneratorStatus() == 3 for i in range(p.getParents().size()))
    ]
    final = sorted(
        (p for p in particles if p.getGeneratorStatus() == 1 and abs(p.getPDG()) == 13),
        key=lambda p: -p.getEnergy(),
    )[:2]
    if len(hard) != 2 or len(final) != 2:
        return None
    muons = {
        "hard": sum(four_vector(p) for p in hard),
        "final": sum(four_vector(p) for p in final),
        "reco": four_vector(pair.getElementAt(0)) + four_vector(pair.getElementAt(1)),
    }

    masses = {
        f"m_recoil_{level}": mass(initial[init] - muons[mu])
        for level, (_, init, mu) in LEVELS.items()
    }
    masses.update({f"m_ll_{mu}": mass(muons[mu]) for mu in ("hard", "final", "reco")})
    return masses


def extract(path: Path) -> Path:
    from pyLCIO import IOIMPL  # imported per worker process

    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(str(path))
    rows = [m for event in reader if (m := event_masses(event)) is not None]
    reader.close()

    out = path.with_name(f"{path.name.removesuffix('.slcio')}_recoil.npz")
    np.savez(out, **{key: np.array([r[key] for r in rows]) for key in rows[0]})
    return out


def signal_files(reco_dir: Path, ilc_polarisation: str) -> dict[str, list[Path]]:
    files = {ILC: [], FCCEE: []}
    for f in sorted(reco_dir.glob("*.slcio")):
        s = parse_sample(f)
        if (
            s.process == SIGNAL
            and s.isr
            and (s.collider == FCCEE or s.polarisation == ilc_polarisation)
        ):
            files[s.collider].append(f)
    return files


def load(files: list[Path], jobs: int) -> dict[str, np.ndarray]:
    missing = [f for f in files if not cache_path(f).is_file()]
    if missing:
        # spawn: fresh interpreters, so ROOT/pyLCIO are initialised per process
        with ProcessPoolExecutor(max_workers=jobs, mp_context=get_context("spawn")) as pool:
            list(pool.map(extract, missing))
    data = [np.load(cache_path(f)) for f in files]
    return {key: np.concatenate([d[key] for d in data]) for key in data[0].files}


def cache_path(f: Path) -> Path:
    return f.with_name(f"{f.name.removesuffix('.slcio')}_recoil.npz")


def peak_stats(
    values: np.ndarray, lo: float, hi: float, bandwidth: float = 0.1
) -> dict[str, float]:
    """Mode and FWHM of a Gaussian kernel density estimate (adds ~0.24 GeV in quadrature to the
    FWHM for bandwidth 0.1 GeV, so FWHMs below ~0.3 GeV are not resolved)."""
    grid = np.arange(lo, hi, 0.01)
    inside = values[(values > lo - 1) & (values < hi + 1)]
    density = np.zeros_like(grid)
    for chunk in np.array_split(inside, max(1, len(inside) // 2000)):
        density += np.exp(-0.5 * ((grid[:, None] - chunk[None, :]) / bandwidth) ** 2).sum(axis=1)
    above = grid[density >= density.max() / 2]
    return {
        "mode": float(grid[density.argmax()]),
        "fwhm": float(above.max() - above.min()),
        "median": float(np.median(values)),
    }


def style_axes(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9)


def plot_overview(data: dict[str, dict], out: Path, ilc_polarisation: str, title: bool = True):
    """Reconstructed di-muon mass (lines) and recoil mass (filled) for both colliders."""
    bins = np.arange(69.5, 160.5, 1.0)  # centred on integers, so m_H = 125 is a bin centre
    fig, ax = plt.subplots(figsize=(8, 5.2))
    for collider, d in data.items():
        color = COLLIDER_COLORS[collider]
        weights = np.full(len(d["m_ll_reco"]), 1 / len(d["m_ll_reco"]))
        label = COLLIDER_LABELS[collider]
        ax.hist(
            d["m_recoil_reco"],
            bins=bins,
            weights=weights,
            histtype="stepfilled",
            color=color,
            alpha=0.25,
            linewidth=0,
        )
        ax.hist(
            d["m_recoil_reco"],
            bins=bins,
            weights=weights,
            histtype="step",
            color=color,
            linewidth=1.5,
            label=f"{label}: recoil mass",
        )
        ax.hist(
            d["m_ll_reco"],
            bins=bins,
            weights=weights,
            histtype="step",
            color=color,
            linewidth=2,
            linestyle=(0, (4, 1.5)),
            label=rf"{label}: $m_{{\mu\mu}}$",
        )
    for m in (M_Z, M_H):
        ax.axvline(m, color=MUTED, linestyle=":", linewidth=1)
    ax.text(M_Z + 0.8, 0.97, r"$m_Z$", transform=ax.get_xaxis_transform(), color=MUTED)
    ax.text(M_H - 0.8, 0.97, r"$m_H$", transform=ax.get_xaxis_transform(), ha="right", color=MUTED)
    ax.set_xlim(bins[0], bins[-1])
    ax.set_xlabel(r"$m_{\mu\mu}$, $M_\mathrm{recoil}$ [GeV]", color=INK)
    ax.set_ylabel("fraction of events / GeV", color=INK)
    ax.legend(frameon=False, fontsize=9, loc="center right")
    ax.set_ylim(0, None)
    if title:
        fig.suptitle(
            rf"$ZH \to \mu\mu + \mathrm{{inv}}$, SGV, events with a reconstructed $\mu^+\mu^-$ pair"
            f"\nILC: {ilc_polarisation}, ILD_l5_o1_v02; FCC-ee: unpolarised, ILD_FCCee_v01",
            fontsize=10,
            color=INK,
            x=0.02,
            ha="left",
        )
    style_axes(ax)
    fig.tight_layout()
    fig.savefig(out.with_suffix(".pdf"))
    fig.savefig(out.with_suffix(".png"), dpi=150)
    plt.close(fig)


def plot_breakdown(data: dict[str, dict], out: Path):
    """Recoil mass with the effects switched on one at a time: one column per collider, peak
    region (linear) on top, full range (log) below."""
    views = [  # (bins, log y, y label)
        (np.arange(119.875, 132.2, 0.25), False, "fraction of events / 0.25 GeV"),
        (np.arange(114.75, 160.25, 0.5), True, "fraction of events / 0.5 GeV"),
    ]
    shades = {"isr": "#b3b2aa", "spectrum": "#7d7c74", "fsr": "#3e3d38"}  # light -> dark
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharey="row")
    for col, (collider, d) in enumerate(data.items()):
        n = len(d["m_recoil_reco"])
        for row, (bins, log, ylabel) in enumerate(views):
            ax = axes[row, col]
            for level, (label, _, _) in LEVELS.items():
                if level == "hard":
                    continue  # a delta function at m_H (width 4 MeV)
                is_reco = level == "reco"
                ax.hist(
                    d[f"m_recoil_{level}"],
                    bins=bins,
                    weights=np.full(n, 1 / n),
                    histtype="step",
                    color=COLLIDER_COLORS[collider] if is_reco else shades[level],
                    linewidth=2.2 if is_reco else 1.4,
                    label=label,
                )
            ax.axvline(M_H, color=MUTED, linestyle=":", linewidth=1)
            ax.set_xlim(bins[0], bins[-1])
            if log:
                ax.set_yscale("log")
                ax.set_ylim(1e-4, 1)
            if col == 0:
                ax.set_ylabel(ylabel, color=INK)
            style_axes(ax)
        axes[0, col].set_title(COLLIDER_LABELS[collider], fontsize=11, color=INK, loc="left")
        axes[1, col].set_xlabel(r"$M_\mathrm{recoil}$ [GeV]", color=INK)
        axes[0, col].legend(frameon=False, fontsize=9, loc="upper right")
    fig.suptitle(
        "Recoil mass against the muon pair with the effects added one at a time; "
        "'+ ISR' uses the beams after the beam spectrum, all others the nominal beams",
        fontsize=10,
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(out.with_suffix(".pdf"))
    fig.savefig(out.with_suffix(".png"), dpi=150)
    plt.close(fig)


def print_table(data: dict[str, dict]):
    print(f"{'quantity':28s}" + "".join(f"{COLLIDER_LABELS[c]:>34s}" for c in data))
    print(f"{'':28s}" + "".join(f"{'mode  FWHM  median  >140 GeV':>34s}" for _ in data))
    rows = [
        (f"recoil {label}", f"m_recoil_{lvl}", 115, 160) for lvl, (label, _, _) in LEVELS.items()
    ]
    rows += [(f"m_mumu {mu}", f"m_ll_{mu}", 70, 110) for mu in ("hard", "final", "reco")]
    for name, key, lo, hi in rows:
        line = f"{name:28s}"
        for d in data.values():
            s = peak_stats(d[key], lo, hi)
            tail = np.mean(d[key] > 140) if key.startswith("m_recoil") else np.nan
            line += f"{s['mode']:12.2f}{s['fwhm']:6.2f}{s['median']:8.2f}{tail:8.3f}"
        print(line)
    print("n events:", {COLLIDER_LABELS[c]: len(d["m_ll_reco"]) for c, d in data.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ilc-polarisation", default="eL.pR", choices=("eL.pR", "eR.pL"))
    parser.add_argument("--out", type=Path, help=f"Default: $dtDir/{RECO_SUBDIR}/plots")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--no-title", action="store_true", help="Omit the overview title (slides)")
    args = parser.parse_args()

    reco_dir = data_dir() / RECO_SUBDIR
    out_dir = args.out or reco_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    files = signal_files(reco_dir, args.ilc_polarisation)
    data = {collider: load(f, args.jobs) for collider, f in files.items() if f}
    print_table(data)
    plot_overview(data, out_dir / "recoil_ilc_vs_fcc", args.ilc_polarisation, not args.no_title)
    plot_breakdown(data, out_dir / "recoil_breakdown")
    print(f"-> {out_dir}/recoil_ilc_vs_fcc.png, recoil_breakdown.png")


if __name__ == "__main__":
    main()
