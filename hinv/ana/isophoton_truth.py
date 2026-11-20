"""Truth study of the isolated photon tagging (ISOPhotons of steering/llrecoil.py).

For each reco file, three record types are extracted and stored as <out_dir>/<file>_isophoton.npz:

- truth photons: generator photons (status 1) above --e-min-truth, with their origin, energy,
  polar angle, whether they were reconstructed as a photon PFO (type 22) and whether that PFO
  was tagged as isolated
- tagged photons: the ISOPhotons, with the origin and PDG code of their best-matching MC
  particle (RecoMCTruthLink), whether LeptonPairingCombined recovered them into a lepton, and
  the angle to the nearest paired lepton
- events: the recoil mass against the lepton pair, before and after also subtracting the tagged
  photons that were not recovered into the leptons. As in extract_observables, the initial
  state is the nominal one (beam particles before beam spectrum and ISR), which an ISR photon
  leaves too high; subtracting a tagged ISR photon gives the initial state of the hard process.

Origins follow the MC record of the ILD WHIZARD samples: ISR photons are the daughters of the
incoming e+/e- after the beam spectrum (whose parents are the beams, generator status 4); FSR
photons are radiated by a final-state charged lepton (Pythia shower); "decay" photons come from
any other particle, e.g. a pi0 of a tau decay.

The summary groups the files by sample, prints the composition and efficiencies, and writes
plots to <out_dir>/isophoton_truth_<collider>.pdf.

Usage (key4hep sourced):
    python -m hinv.ana.isophoton_truth [<reco_dir>] [--out-dir DIR] [--jobs N] [--summary-only]
    <reco_dir> defaults to $dtDir/<RECO_SUBDIR> (see paths.py), DIR to <reco_dir>/isophoton_truth.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from hinv.ana.extract_observables import cos_theta, four_vector, initial_state, mass
from hinv.paths import RECO_SUBDIR, data_dir
from hinv.samples import FCCEE, parse_sample

ORIGINS = ("unmatched", "ISR", "FSR", "decay", "not a photon")
UNMATCHED, ISR, FSR, DECAY, NOT_PHOTON = range(len(ORIGINS))
CHARGED_LEPTONS = (11, 13, 15)

# categorical slots of the dataviz reference palette, in fixed order: photon origins first, then
# the true particle types of tagged objects that are not photons
COLORS = {"ISR": "#2a78d6", "FSR": "#eb6834", "decay": "#1baf7a"}
OTHER_COLORS = ("#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
PARTICLE_NAMES = {
    11: r"$e^\pm$",
    13: r"$\mu^\pm$",
    211: r"$\pi^\pm$",
    321: r"$K^\pm$",
    2212: r"$p$",
    2112: r"$n$",
    130: r"$K^0_L$",
}

FONT_SCALE = 1.75  # relative to the matplotlib defaults
TRUTH_LABEL = "MC truth"


def photon_origin(mc) -> int:
    """Origin of a generator photon from its first parent, see the module docstring."""
    parents = mc.getParents()
    if len(parents) == 0:
        return DECAY
    parent = parents[0]
    if abs(parent.getPDG()) == 11 and any(
        grand.getGeneratorStatus() == 4 for grand in parent.getParents()
    ):
        return ISR
    if abs(parent.getPDG()) in CHARGED_LEPTONS:
        return FSR
    return DECAY


def tagged_origin(mc) -> int:
    if mc is None:
        return UNMATCHED
    return photon_origin(mc) if mc.getPDG() == 22 else NOT_PHOTON


def best_links(event, name: str) -> dict:
    """Maps id(from) -> `to` object of the link with the largest weight."""
    best = {}
    links = event.getCollection(name)
    for i in range(links.getNumberOfElements()):
        link = links.getElementAt(i)
        key = link.getFrom().id()
        if key not in best or link.getWeight() > best[key][1]:
            best[key] = (link.getTo(), link.getWeight())
    return {key: to for key, (to, _) in best.items()}


def elements(event, name: str) -> list:
    try:
        col = event.getCollection(name)
    except Exception:
        return []
    return [col.getElementAt(i) for i in range(col.getNumberOfElements())]


def max_cos_angle(v, others) -> float:
    """Largest cos(angle) between the momentum of v and any of the four-vectors in others."""
    cosines = [
        v[1:] @ o[1:] / (np.linalg.norm(v[1:]) * np.linalg.norm(o[1:]))
        for o in others
        if np.linalg.norm(o[1:]) > 0
    ]
    return max(cosines) if cosines else np.nan


def process_file(path: Path, out_dir: Path, e_min_truth: float) -> str:
    from pyLCIO import IOIMPL  # imported per worker process

    truth = defaultdict(list)
    tagged = defaultdict(list)
    events = defaultdict(list)

    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(str(path))
    for i_event, event in enumerate(reader):
        mc_particles = elements(event, "MCParticlesSkimmed")
        mc_to_reco = best_links(event, "MCTruthRecoLink")
        reco_to_mc = best_links(event, "RecoMCTruthLink")
        iso_photons = elements(event, "ISOPhotons")
        iso_ids = {p.id() for p in iso_photons}
        lepton_pair = elements(event, "LeptonPair")
        recovered = {d.id() for lep in lepton_pair for d in lep.getParticles()}
        paired_leptons = [four_vector(p) for p in elements(event, "IsoLeptonPair")]

        charged_final = [
            four_vector(p)
            for p in mc_particles
            if p.getGeneratorStatus() == 1 and p.getCharge() != 0
        ]
        e_isr = 0.0
        for mc in mc_particles:
            if mc.getGeneratorStatus() != 1 or mc.getPDG() != 22:
                continue
            origin = photon_origin(mc)
            if origin == ISR:
                e_isr += mc.getEnergy()
            if mc.getEnergy() < e_min_truth:
                continue
            v = four_vector(mc)
            reco = mc_to_reco.get(mc.id())
            truth["event"].append(i_event)
            truth["origin"].append(origin)
            truth["e"].append(mc.getEnergy())
            truth["cos"].append(cos_theta(v))
            truth["cos_charged"].append(max_cos_angle(v, charged_final))
            truth["reco_photon"].append(reco is not None and reco.getType() == 22)
            truth["tagged"].append(reco is not None and reco.id() in iso_ids)

        for photon in iso_photons:
            v = four_vector(photon)
            mc = reco_to_mc.get(photon.id())
            tagged["event"].append(i_event)
            tagged["origin"].append(tagged_origin(mc))
            tagged["pdg"].append(mc.getPDG() if mc is not None else 0)
            tagged["e"].append(v[0])
            tagged["e_true"].append(mc.getEnergy() if mc is not None else np.nan)
            tagged["cos"].append(cos_theta(v))
            tagged["recovered"].append(photon.id() in recovered)
            tagged["cos_lepton"].append(max_cos_angle(v, paired_leptons))

        p_init = initial_state(event.getCollection("MCParticlesSkimmed"))
        has_pair = len(lepton_pair) == 2
        p_ll = sum(four_vector(p) for p in lepton_pair) if has_pair else np.zeros(4)
        p_photons = sum(
            (four_vector(p) for p in iso_photons if p.id() not in recovered), np.zeros(4)
        )
        events["has_pair"].append(has_pair)
        events["n_iso"].append(len(iso_photons))
        events["e_isr_true"].append(e_isr)
        events["m_recoil"].append(mass(p_init - p_ll) if has_pair else np.nan)
        events["m_recoil_corr"].append(mass(p_init - p_ll - p_photons) if has_pair else np.nan)
    reader.close()

    out = out_dir / f"{path.stem}_isophoton.npz"
    np.savez(
        out,
        **{f"truth_{k}": np.array(v) for k, v in truth.items()},
        **{f"tagged_{k}": np.array(v) for k, v in tagged.items()},
        **{f"events_{k}": np.array(v) for k, v in events.items()},
    )
    return f"{path.name}: {len(events['n_iso'])} events, {len(tagged['e'])} tagged photons"


# --- summary --------------------------------------------------------------------------------


def load(out_dir: Path) -> dict:
    """Concatenates the npz files per sample, keyed by (collider, energy, process, pol.)."""
    samples = defaultdict(lambda: defaultdict(list))
    for f in sorted(out_dir.glob("*_isophoton.npz")):
        s = parse_sample(f)
        with np.load(f) as data:
            for key in data.files:
                samples[(s.collider, s.energy, s.process, s.polarisation)][key].append(data[key])
    return {
        key: {k: np.concatenate(v) if v[0].ndim else np.array(v) for k, v in arrays.items()}
        for key, arrays in samples.items()
    }


def fraction(k: int, n: int) -> str:
    return f"{100 * k / n:5.1f}%" if n else "    - "


def print_summary(samples: dict, accept_cos: float) -> None:
    head = f"{'sample':38s} {'events':>7s} {'w/ tag':>7s} {'tags':>6s} " + " ".join(
        f"{o:>12s}" for o in ORIGINS
    )
    print("\nTagged photons by origin of the matched MC particle\n" + head)
    for (collider, energy, process, pol), d in sorted(samples.items()):
        origin = d.get("tagged_origin", np.array([], int))
        n_events = len(d["events_n_iso"])
        counts = [int(np.sum(origin == i)) for i in range(len(ORIGINS))]
        print(
            f"{collider + ' ' + str(energy) + ' ' + process + ' ' + str(pol):38s} {n_events:7d} "
            f"{fraction(np.sum(d['events_n_iso'] > 0), n_events):>7s} {len(origin):6d} "
            + " ".join(f"{fraction(c, len(origin)):>12s}" for c in counts)
        )

    print(
        f"\nTruth photons with |cos(theta)| < {accept_cos}: fraction reconstructed as photon PFO"
        " / tagged as isolated"
    )
    print(
        f"{'sample':38s}" + f" {'ISR':>8s} {'reco':>7s} {'tagged':>7s}"
        f" {'FSR':>8s} {'reco':>7s} {'tagged':>7s}"
    )
    for (collider, energy, process, pol), d in sorted(samples.items()):
        if "truth_origin" not in d:
            continue
        row = f"{collider + ' ' + str(energy) + ' ' + process + ' ' + str(pol):38s}"
        for origin in (ISR, FSR):
            sel = (d["truth_origin"] == origin) & (np.abs(d["truth_cos"]) < accept_cos)
            n = int(sel.sum())
            row += (
                f" {n:8d} {fraction(d['truth_reco_photon'][sel].sum(), n):>7s}"
                f" {fraction(d['truth_tagged'][sel].sum(), n):>7s}"
            )
        print(row)

    print("\nTagged photons that LeptonPairingCombined also recovered into a lepton")
    for (collider, energy, process, pol), d in sorted(samples.items()):
        recovered = d.get("tagged_recovered", np.array([], bool))
        print(
            f"{collider + ' ' + str(energy) + ' ' + process + ' ' + str(pol):38s} "
            f"{int(recovered.sum()):6d} / {len(recovered)}"
        )


def efficiency(passed: np.ndarray, x: np.ndarray, bins: np.ndarray):
    n, _ = np.histogram(x, bins)
    k, _ = np.histogram(x[passed], bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        eff = k / n
        err = np.sqrt(eff * (1 - eff) / n)
    return eff, err


def particle_name(pdg: int) -> str:
    return PARTICLE_NAMES.get(abs(pdg), f"PDG {abs(pdg)}")


def mark_truth(ax) -> None:
    """Marks a panel that uses MC truth information."""
    ax.set_title(TRUTH_LABEL, loc="right", fontsize="medium", style="italic", color="#5f5e5a")


def plot_collider(samples: dict, collider: str, out: Path) -> bool:
    """Writes the plots of one collider to out; returns False if it has no samples."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    selected = {k: d for k, d in samples.items() if k[0] == collider}
    if not selected:
        return False
    energy = next(iter(selected))[1]
    # efficiencies are detector properties: merge all samples and polarisations
    truth = {
        key: np.concatenate([d[f"truth_{key}"] for d in selected.values() if "truth_e" in d])
        for key in ("origin", "e", "cos", "reco_photon", "tagged")
    }
    title = f"ILD@{collider}, {energy} GeV, SGV"

    base = plt.rcParams["font.size"]
    with plt.rc_context({"font.size": FONT_SCALE * base}), PdfPages(out) as pdf:
        for variable, bins, label in (
            ("cos", np.linspace(0, 1, 41), r"$|\cos\theta_\gamma^\mathrm{true}|$"),
            ("e", np.linspace(5, 125, 25), r"$E_\gamma^\mathrm{true}$ [GeV]"),
        ):
            fig, ax = plt.subplots(figsize=(9, 6.5))
            centres = 0.5 * (bins[1:] + bins[:-1])
            for origin in (ISR, FSR):
                sel = truth["origin"] == origin
                x = np.abs(truth[variable][sel]) if variable == "cos" else truth[variable][sel]
                if variable == "e":  # restrict to the barrel and endcap
                    keep = np.abs(truth["cos"][sel]) < 0.95
                    x, passed_reco, passed_tag = (
                        x[keep],
                        truth["reco_photon"][sel][keep],
                        truth["tagged"][sel][keep],
                    )
                else:
                    passed_reco, passed_tag = truth["reco_photon"][sel], truth["tagged"][sel]
                color = COLORS[ORIGINS[origin]]
                eff, err = efficiency(passed_tag, x, bins)
                ax.errorbar(
                    centres,
                    eff,
                    err,
                    fmt="o",
                    ms=4,
                    lw=1.5,
                    color=color,
                    label=f"{ORIGINS[origin]}: tagged isolated",
                )
                eff, _ = efficiency(passed_reco, x, bins)
                ax.step(
                    centres,
                    eff,
                    where="mid",
                    lw=1.5,
                    ls="--",
                    color=color,
                    label=f"{ORIGINS[origin]}: photon PFO",
                )
            ax.set_xlabel(label)
            ax.set_ylabel("efficiency")
            ax.set_ylim(0, 1.05)
            note = "" if variable == "cos" else r", $|\cos\theta| < 0.95$"
            ax.set_title(f"{title}\ntrue photons $E > 5$ GeV{note}", loc="left", fontsize="medium")
            mark_truth(ax)
            ax.grid(alpha=0.3, lw=0.5)
            ax.legend(fontsize="small", frameon=False)
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

        for key, d in sorted(selected.items()):
            if "tagged_e" not in d or len(d["tagged_e"]) == 0:
                continue
            process, pol = key[2], key[3]
            fig, axes = plt.subplots(1, 2, figsize=(16, 7))
            bins = np.linspace(0, 125, 51)
            origin, pdg = d["tagged_origin"], np.abs(d["tagged_pdg"])
            groups = [
                (rf"$\gamma$ {ORIGINS[o]}", COLORS[ORIGINS[o]], origin == o)
                for o in (ISR, FSR, DECAY)
                if np.any(origin == o)
            ]
            others = sorted(set(pdg[origin == NOT_PHOTON]), key=lambda c: -np.sum(pdg == c))
            groups += [
                (
                    particle_name(c),
                    OTHER_COLORS[i % len(OTHER_COLORS)],
                    (origin == NOT_PHOTON) & (pdg == c),
                )
                for i, c in enumerate(others)
            ]
            if np.any(origin == UNMATCHED):
                groups.append(("unmatched", "#898781", origin == UNMATCHED))
            axes[0].hist(
                [d["tagged_e"][sel] for _, _, sel in groups],
                bins,
                stacked=True,
                color=[c for _, c, _ in groups],
                label=[n for n, _, _ in groups],
                edgecolor="white",
                linewidth=0.5,
            )
            mark_truth(axes[0])
            axes[0].set_xlabel(r"$E$ of tagged photons (reco) [GeV]")
            axes[0].set_ylabel("photons / 2.5 GeV")
            axes[0].legend(
                title="matched MC particle",
                fontsize="small",
                title_fontsize="small",
                frameon=False,
            )

            tagged_events = d["events_has_pair"] & (d["events_n_iso"] > 0)
            bins = np.linspace(-50, 200, 51)
            for column, label, style in (
                ("events_m_recoil", "lepton pair only", "-"),
                ("events_m_recoil_corr", "minus tagged photons", "--"),
            ):
                axes[1].hist(
                    d[column][tagged_events],
                    bins,
                    histtype="step",
                    lw=1.5,
                    ls=style,
                    color="#2a78d6" if style == "-" else "#eb6834",
                    label=label,
                )
            axes[1].set_xlabel(r"$m_\mathrm{recoil}$ [GeV], events with a tagged photon")
            axes[1].set_ylabel("events / 5 GeV")
            axes[1].legend(fontsize="small", frameon=False)
            for ax in axes:
                ax.grid(alpha=0.3, lw=0.5)
            fig.suptitle(f"{title}: {process} {pol or ''}")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

            plot_purity(d, f"{title}: {process} {pol or ''}", pdf)
    return True


# bins of the purity maps: finer towards the beam, where untracked e+- are tagged as photons
PURITY_COS_BINS = np.array([0, 0.3, 0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.998, 1])
PURITY_E_BINS = np.array([5, 10, 15, 20, 30, 40, 60, 80, 100, 110, 120, 130])
PURITY_MIN_COUNT = 10  # bins with fewer tagged photons are left empty


def plot_purity(d: dict, title: str, pdf) -> None:
    """Heatmaps of the purity (true photons) and ISR fraction of the tagged photons in bins of
    the reconstructed |cos(theta)| and energy; one page of pdf."""
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("#f0efec")

    x = np.digitize(np.abs(d["tagged_cos"]), PURITY_COS_BINS) - 1
    y = np.digitize(d["tagged_e"], PURITY_E_BINS) - 1
    shape = (len(PURITY_E_BINS) - 1, len(PURITY_COS_BINS) - 1)
    inside = (x >= 0) & (x < shape[1]) & (y >= 0) & (y < shape[0])

    def count(mask):
        n = np.zeros(shape)
        np.add.at(n, (y[inside & mask], x[inside & mask]), 1)
        return n

    n_all = count(np.ones_like(x, bool))
    origin = d["tagged_origin"]
    maps = (
        (
            "purity: true photons / tagged",
            count((origin == ISR) | (origin == FSR) | (origin == DECAY)),
        ),
        ("ISR photons / tagged", count(origin == ISR)),
    )

    fig, axes = plt.subplots(1, 2, figsize=(22, 10))
    for ax, (label, n_pass) in zip(axes, maps):
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = np.where(n_all >= PURITY_MIN_COUNT, n_pass / n_all, np.nan)
        image = ax.pcolormesh(
            np.ma.masked_invalid(ratio), cmap=cmap, vmin=0, vmax=1, edgecolors="white", linewidth=1
        )
        for (i, j), value in np.ndenumerate(ratio):
            if not np.isnan(value):
                # viridis is dark at low values
                ax.text(
                    j + 0.5,
                    i + 0.5,
                    f"{value:.2f}",
                    ha="center",
                    va="center",
                    fontsize="x-small",
                    color="white" if value < 0.6 else "#1a1a19",
                )
        ax.set_xticks(
            np.arange(shape[1] + 1),
            [f"{b:g}" for b in PURITY_COS_BINS],
            fontsize="small",
            rotation=45,
        )
        ax.set_yticks(np.arange(shape[0] + 1), [f"{b:g}" for b in PURITY_E_BINS], fontsize="small")
        ax.set_xlabel(r"$|\cos\theta_\gamma|$ (reco, variable bins)")
        ax.set_ylabel(r"$E_\gamma$ (reco) [GeV]")
        fig.colorbar(image, ax=ax, label=label, fraction=0.046, pad=0.02)
        mark_truth(ax)
    fig.suptitle(f"{title}: tagged photons, empty bins: < {PURITY_MIN_COUNT} photons")
    fig.tight_layout()
    pdf.savefig(fig)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("reco_dir", type=Path, nargs="?", help=f"Default: $dtDir/{RECO_SUBDIR}")
    parser.add_argument("--out-dir", type=Path, help="Default: <reco_dir>/isophoton_truth")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel processes (default: 8)")
    parser.add_argument(
        "--e-min-truth",
        type=float,
        default=5.0,
        help="Minimum energy of the truth photons [GeV] (default: 5)",
    )
    parser.add_argument(
        "--accept-cos",
        type=float,
        default=0.95,
        help="|cos(theta)| acceptance of the efficiency table (default: 0.95)",
    )
    parser.add_argument(
        "--summary-only", action="store_true", help="Only summarise existing npz files"
    )
    args = parser.parse_args()

    reco_dir = (args.reco_dir or data_dir() / RECO_SUBDIR).resolve()
    out_dir = (args.out_dir or reco_dir / "isophoton_truth").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.summary_only:
        files = sorted(reco_dir.glob("*.slcio"))
        if not files:
            sys.exit(f"No .slcio files found in {reco_dir}")
        work = partial(process_file, out_dir=out_dir, e_min_truth=args.e_min_truth)
        # spawn: fresh interpreters, so ROOT/pyLCIO are initialised per process
        with ProcessPoolExecutor(max_workers=args.jobs, mp_context=get_context("spawn")) as pool:
            for message in pool.map(work, files):
                print(message)

    samples = load(out_dir)
    print_summary(samples, args.accept_cos)
    for collider in ("ILC", FCCEE):
        out = out_dir / f"isophoton_truth_{collider.replace('-', '')}.pdf"
        if plot_collider(samples, collider, out):
            print(f"Plots: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
