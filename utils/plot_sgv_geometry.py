"""Draw SGV geometries (.inp) as an r-z quarter view, optionally with rays from the IP.

Several geometries are drawn side by side on shared axes, e.g. to compare detector variants.
Rays from the IP mark polar angles, given in mrad (stay-clear cones of the MDI), as
pseudorapidity eta = -ln tan(theta/2), or as |cos(theta)|. For massless particles, eta equals
the rapidity y. Rays are drawn with respect to the detector (solenoid) axis, a beam crossing
angle is not taken into account.

What is drawn:
    - barrel/forward tracking layers as lines (sensitive layers thicker than passive ones),
    - layer groups from REPEAT blocks and layers named *-MAT (calorimeter and yoke material)
      as filled envelopes,
    - calorimetry layers without *-MAT material as filled blocks when their depth is known (a
      FORWARD_CALORIMETRY layer paired with a BARREL_CALORIMETRY "inside" layer), else as lines.

Usage:
    python utils/plot_sgv_geometry.py sgv_geometries/sgv_geo_fullsim_ildfcc_v{1,2}.inp \
        --titles "ILD@FCCee (V1)" "ILD@FCCee (V2)" --z-range 0 300 --r-range 0 100 \
        --mrad 150 110 100 --eta 2 3 -o ild_fcc_mdi.pdf
    python utils/plot_sgv_geometry.py sgv_geometries/sgv_geo_ild_ilc.inp --dump
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

BARREL_SECTIONS = ("BARREL_TRACKING", "BARREL_CALORIMETRY")
TRACKING_SECTIONS = ("BARREL_TRACKING", "FORWARD_TRACKING")
# SGV puts ZMAX=999.9 on the beam pipe: ignore such sentinel extents for the default view.
SENTINEL_EXTENT = 900.0

INK = "#1b1b1a"
MUTED = "#6b6a63"
GRID = "#e4e3de"
PASSIVE = "#b07a4a"
MRAD_COLOR = "#1b1b1a"
ETA_COLOR = "#2a6fdb"
COSTHETA_COLOR = "#b5179e"
LABEL_POSITIONS = (0.98, 0.78, 0.58)  # along the ray, as fraction of its visible length

# (legend label, layer name pattern, colour); first match wins, order matters
CATEGORIES = [
    ("Beam pipe", r"^(BEAMPIPE|BP)", "#e69f00"),
    ("LumiCal", r"^(LCAL|LUMI)", "#ff6347"),
    ("BeamCal", r"^BEAMCAL", "#9b59b6"),
    ("LHCAL", r"^LHCAL", "#ee82ee"),
    ("Support / services", r"SUP|CRYO|READOUT|CABLE|INTERLINK|WALL|ENDP|INST|BACK", PASSIVE),
    ("Vertex detector", r"^V[XT]D", "#e41a1c"),
    ("Silicon trackers", r"^(SIT|SET|FTD|ETD|OT|IT)", "#7b1fa2"),
    ("TPC", r"^TPC", "#f2d600"),
    ("ECAL", r"^ECAL", "#1f4fd8"),
    ("HCAL", r"^HCAL", "#2e8b2e"),
    ("Magnet", r"^(MAGNET|COIL|SOLENOID)", "#8c8c8c"),
    ("Yoke / muon", r"^(YOKE|MU)", "#4d4d4d"),
]
OTHER = ("Other", "#a0a0a0")


@dataclass
class Layer:
    name: str
    section: str
    z0: float
    z1: float
    r0: float
    r1: float
    x0: float | None = None
    code: int = 0
    repeated: bool = False

    @property
    def barrel(self) -> bool:
        return self.section in BARREL_SECTIONS

    @property
    def sensitive(self) -> bool:
        return self.section in TRACKING_SECTIONS and self.code > 0


@dataclass
class Geometry:
    path: Path
    bfield: float | None
    layers: list[Layer]


@dataclass
class Shape:
    """A drawable: a rectangle in (z, r); a line when one extent is zero."""

    name: str
    z0: float
    z1: float
    r0: float
    r1: float
    filled: bool
    sensitive: bool = False


# --------------------------------------------------------------------------------------------
# Parsing


KEYWORD = re.compile(r"^\s*([A-Z_]+)\s*:(.*)$", re.IGNORECASE)
KEY_VALUE = re.compile(r"([A-Z_][A-Z_0-9]*)\s*=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?)")
KNOWN_KEYWORDS = {
    "BF",
    "TYPE",
    "LAYER",
    "GEOMETRY",
    "MATERIAL",
    "MEASUREMENT",
    "REPEAT",
    "ENDREPEAT",
}


def key_values(text: str) -> dict[str, float]:
    return {
        k.upper(): float(v.replace("d", "e").replace("D", "e")) for k, v in KEY_VALUE.findall(text)
    }


def is_comment(line: str) -> bool:
    # Fortran style: 'C' or '*' in column 1, followed by a blank (or nothing)
    return bool(line) and line[0] in "Cc*!" and (len(line) == 1 or not line[1].isalnum())


def parse_sgv(path: Path) -> Geometry:
    """Parse the geometry part of an SGV .inp file (layer extents, X0, measurement code)."""
    bfield = None
    section = None
    layers: list[Layer] = []
    current: dict | None = None
    last_name = ""
    last_keyword = None

    def finalize():
        nonlocal current
        if current is None:
            return
        if "geometry" not in current:
            warnings.warn(f"{path.name}: layer {current['name']!r} without GEOMETRY, skipped")
            current = None
            return
        geo = current["geometry"]
        barrel = current["section"] in BARREL_SECTIONS
        try:
            if barrel:
                base = (geo["ZMIN"], geo["ZMAX"], geo["R"], geo["R"])
            else:
                base = (geo["Z"], geo["Z"], geo["RMIN"], geo["RMAX"])
        except KeyError as err:
            warnings.warn(f"{path.name}: layer {current['name']!r} lacks {err}, skipped")
            current = None
            return
        rep = current.get("repeat", {})
        times = int(rep.get("TIMES", 1))
        # The step goes along the layer's normal (r for barrel, z for forward layers), whatever
        # the keyword: some files use DELTA_R inside forward REPEAT blocks.
        step = rep.get("DELTA_R" if barrel else "DELTA_Z")
        if step is None:
            step = rep.get("DELTA_Z" if barrel else "DELTA_R", 0.0)
        for i in range(times):
            z0, z1, r0, r1 = base
            if barrel:
                r0 = r1 = r0 + i * step
            else:
                z0 = z1 = z0 + i * step
            layers.append(
                Layer(
                    name=current["name"],
                    section=current["section"],
                    z0=z0,
                    z1=z1,
                    r0=r0,
                    r1=r1,
                    x0=current.get("material", {}).get("X0"),
                    code=int(current.get("measurement", {}).get("CODE", 0)),
                    repeated=times > 1,
                )
            )
        current = None

    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if not line.strip() or is_comment(line):
            continue
        m = KEYWORD.match(line)
        keyword = m.group(1).upper() if m else None
        if keyword not in KNOWN_KEYWORDS:
            # continuation of the previous keyword (e.g. long MEASUREMENT lists) or stray text
            if last_keyword in ("GEOMETRY", "MATERIAL", "MEASUREMENT") and current is not None:
                current.setdefault(last_keyword.lower(), {}).update(key_values(line))
            continue
        rest = m.group(2)
        if keyword == "BF":
            bfield = key_values(rest).get("BFIELD")
        elif keyword == "TYPE":
            finalize()
            section = rest.strip().upper()
        elif keyword == "LAYER":
            finalize()
            name = rest.strip() or last_name  # an unnamed LAYER continues the previous name
            last_name = name
            current = {"name": name, "section": section}
        elif keyword in ("GEOMETRY", "MATERIAL", "MEASUREMENT", "REPEAT"):
            if current is None:
                warnings.warn(f"{path.name}: {keyword} outside a LAYER: {line.strip()!r}")
            else:
                current.setdefault(keyword.lower(), {}).update(key_values(rest))
        elif keyword == "ENDREPEAT":
            finalize()
        last_keyword = keyword
    finalize()
    return Geometry(path=path, bfield=bfield, layers=layers)


# --------------------------------------------------------------------------------------------
# Layers -> shapes


def close(a: float, b: float, tol: float = 0.5) -> bool:
    return abs(a - b) <= tol


def build_shapes(geo: Geometry) -> list[Shape]:
    shapes: list[Shape] = []
    tracking = [ly for ly in geo.layers if ly.section in TRACKING_SECTIONS]
    calo = [ly for ly in geo.layers if ly.section not in TRACKING_SECTIONS]

    # Envelopes: *-MAT material layers and REPEAT groups (e.g. TPC pad rows)
    groups: dict[tuple[str, bool], list[Layer]] = {}
    for ly in tracking:
        if ly.name.upper().endswith("-MAT") or ly.repeated:
            groups.setdefault((ly.name, ly.barrel), []).append(ly)
    grouped = {id(ly) for lys in groups.values() for ly in lys}
    for (name, _), lys in groups.items():
        shapes.append(
            Shape(
                name=name,
                z0=min(ly.z0 for ly in lys),
                z1=max(ly.z1 for ly in lys),
                r0=min(ly.r0 for ly in lys),
                r1=max(ly.r1 for ly in lys),
                filled=True,
            )
        )
    for ly in tracking:
        if id(ly) not in grouped:
            shapes.append(Shape(ly.name, ly.z0, ly.z1, ly.r0, ly.r1, False, ly.sensitive))

    # Calorimeters: skip those with *-MAT material (already drawn); fill forward calorimeters
    # whose depth is given by a matching barrel "inside" layer (R = RMIN, ZMIN = Z)
    mat_names = {
        name.upper()[: -len("-MAT")] for name, _ in groups if name.upper().endswith("-MAT")
    }
    barrel_calo = [ly for ly in calo if ly.barrel]
    used = set()
    for ly in calo:
        if ly.barrel:
            continue
        partner = next((b for b in barrel_calo if close(b.r0, ly.r0) and close(b.z0, ly.z0)), None)
        if partner is not None:
            used.add(id(partner))
        if ly.name.upper() in mat_names:
            continue
        if partner is not None:
            shapes.append(Shape(ly.name, ly.z0, partner.z1, ly.r0, ly.r1, True))
        else:
            shapes.append(Shape(ly.name, ly.z0, ly.z1, ly.r0, ly.r1, False))
    for ly in barrel_calo:
        if id(ly) in used or ly.name.upper() in mat_names:
            continue
        shapes.append(Shape(ly.name, ly.z0, ly.z1, ly.r0, ly.r1, False))
    return shapes


def category(name: str) -> tuple[str, str]:
    for label, pattern, color in CATEGORIES:
        if re.search(pattern, name, re.IGNORECASE):
            return label, color
    return OTHER


# --------------------------------------------------------------------------------------------
# Rays


@dataclass
class Ray:
    theta: float  # polar angle [rad]
    label: str
    color: str
    linestyle: str


def make_rays(args) -> list[Ray]:
    rays = []
    for mrad in args.mrad or []:
        rays.append(Ray(mrad * 1e-3, f"{mrad:g} mrad", MRAD_COLOR, "--"))
    for eta in args.eta or []:
        rays.append(Ray(2 * math.atan(math.exp(-eta)), rf"$\eta = {eta:g}$", ETA_COLOR, ":"))
    for c in args.costheta or []:
        if not 0 <= c < 1:
            sys.exit(f"--costheta expects values in [0, 1), got {c}")
        rays.append(Ray(math.acos(c), rf"$|\cos\theta| = {c:g}$", COSTHETA_COLOR, "-."))
    for ray in rays:
        if not 0 < ray.theta <= math.pi / 2:
            sys.exit(f"ray {ray.label!r}: polar angle must be in (0, 90 deg]")
    return rays


def draw_ray(ax, ray: Ray, zlim, rlim, label_at: float = 0.98):
    c, s = math.cos(ray.theta), math.sin(ray.theta)
    # distance from the IP to where the ray leaves the view (right or top edge)
    length = min(zlim[1] / c if c > 1e-12 else math.inf, rlim[1] / s)
    ax.plot([0, length * c], [0, length * s], color=ray.color, ls=ray.linestyle, lw=1.1, zorder=5)
    end = label_at * length
    ax.text(
        end * c,
        end * s,
        ray.label,
        color=ray.color,
        fontsize=8,
        ha="right",
        va="bottom",
        rotation=math.degrees(ray.theta),
        rotation_mode="anchor",
        transform_rotates_text=True,
        clip_on=True,
        zorder=6,
        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7),
    )


# --------------------------------------------------------------------------------------------
# Plotting


def default_limits(shapes_per_geo: list[list[Shape]]) -> tuple[tuple, tuple]:
    zs = [
        v for shapes in shapes_per_geo for s in shapes for v in (s.z0, s.z1) if v < SENTINEL_EXTENT
    ]
    rs = [v for shapes in shapes_per_geo for s in shapes for v in (s.r0, s.r1)]
    return (0.0, 1.03 * max(zs)), (0.0, 1.03 * max(rs))


def visible(s: Shape, zlim, rlim) -> bool:
    return s.z1 >= zlim[0] and s.z0 <= zlim[1] and s.r1 >= rlim[0] and s.r0 <= rlim[1]


def draw_geometry(ax, shapes: list[Shape], line_scale: float, zlim, rlim) -> dict[str, str]:
    """Draw the shapes, return the legend entries {label: colour} visible in the view."""
    used = {}
    # fills first, lines on top
    for s in sorted(shapes, key=lambda s: not s.filled):
        label, color = category(s.name)
        if visible(s, zlim, rlim):
            used[label] = color
        if s.filled:
            ax.add_patch(
                Rectangle(
                    (s.z0, s.r0),
                    s.z1 - s.z0,
                    s.r1 - s.r0,
                    facecolor=color,
                    edgecolor="none",
                    alpha=0.85,
                    zorder=1,
                )
            )
        else:
            lw = (2.2 if s.sensitive else 1.4) * line_scale
            ax.plot(
                [s.z0, s.z1],
                [s.r0, s.r1],
                color=color,
                lw=lw,
                solid_capstyle="butt",
                zorder=3 if s.sensitive else 2,
            )
    return used


def style_axes(ax):
    ax.grid(color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_xlabel("z [cm]", color=INK)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Usage:" + __doc__.split("Usage:")[1],
    )
    parser.add_argument("geometries", nargs="+", type=Path, help="SGV .inp geometry files")
    parser.add_argument("-o", "--output", type=Path, default=Path("sgv_geometry.pdf"))
    parser.add_argument("--titles", nargs="+", help="panel titles (default: file names)")
    parser.add_argument("--z-range", nargs=2, type=float, metavar=("ZMIN", "ZMAX"), help="cm")
    parser.add_argument("--r-range", nargs=2, type=float, metavar=("RMIN", "RMAX"), help="cm")
    parser.add_argument("--mrad", nargs="+", type=float, help="rays at polar angles [mrad]")
    parser.add_argument("--eta", nargs="+", type=float, help="rays at pseudorapidities")
    parser.add_argument("--costheta", nargs="+", type=float, help="rays at |cos(theta)|")
    parser.add_argument(
        "--equal", action="store_true", help="equal aspect ratio (true angles of the rays)"
    )
    parser.add_argument("--ncols", type=int, help="panels per row (default: all in one row)")
    parser.add_argument(
        "--panel-size", nargs=2, type=float, default=(6.0, 3.6), metavar=("W", "H"), help="inch"
    )
    parser.add_argument("--line-scale", type=float, default=1.0, help="scale layer line widths")
    parser.add_argument("--no-legend", action="store_true")
    parser.add_argument("--dump", action="store_true", help="print the parsed layers and exit")
    args = parser.parse_args(argv)

    if args.titles and len(args.titles) != len(args.geometries):
        sys.exit("--titles needs one title per geometry")

    geos = [parse_sgv(p) for p in args.geometries]
    if args.dump:
        for geo in geos:
            print(f"# {geo.path}  (B = {geo.bfield} T, {len(geo.layers)} layers)")
            print(
                f"{'section':<20} {'name':<18} {'z0':>8} {'z1':>8} {'r0':>8} {'r1':>8} "
                f"{'X0':>8} code"
            )
            for ly in geo.layers:
                x0 = "-" if ly.x0 is None else f"{ly.x0:.4g}"
                print(
                    f"{ly.section:<20} {ly.name:<18} {ly.z0:8.2f} {ly.z1:8.2f} "
                    f"{ly.r0:8.2f} {ly.r1:8.2f} {x0:>8} {ly.code}"
                )
        return

    shapes_per_geo = [build_shapes(g) for g in geos]
    zlim, rlim = default_limits(shapes_per_geo)
    zlim = tuple(args.z_range) if args.z_range else zlim
    rlim = tuple(args.r_range) if args.r_range else rlim
    rays = make_rays(args)

    n = len(geos)
    ncols = args.ncols or n
    nrows = math.ceil(n / ncols)
    width, height = args.panel_size
    if args.equal:  # panel height follows the data aspect ratio (+ room for labels)
        height = 1.5 + (width - 0.8) * (rlim[1] - rlim[0]) / (zlim[1] - zlim[0])
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(width * ncols, height * nrows + 0.5),
        squeeze=False,
        sharex=True,
        sharey=True,
        layout="constrained",
    )
    legend = {}
    for i, (geo, shapes) in enumerate(zip(geos, shapes_per_geo)):
        ax = axes.flat[i]
        legend.update(draw_geometry(ax, shapes, args.line_scale, zlim, rlim))
        ax.set_xlim(zlim)
        ax.set_ylim(rlim)
        if args.equal:
            ax.set_aspect("equal", adjustable="box")
        # stagger the labels of neighbouring rays along the ray so they do not overlap
        for k, ray in enumerate(sorted(rays, key=lambda r: r.theta)):
            draw_ray(ax, ray, zlim, rlim, label_at=LABEL_POSITIONS[k % len(LABEL_POSITIONS)])
        title = args.titles[i] if args.titles else geo.path.stem
        ax.set_title(title, color=INK, fontsize=11, loc="left")
        if geo.bfield is not None:
            ax.set_title(f"B = {geo.bfield:g} T", color=MUTED, fontsize=8, loc="right")
        style_axes(ax)
        if i % ncols == 0:
            ax.set_ylabel("r [cm]", color=INK)
    for ax in axes.flat[n:]:
        ax.set_visible(False)

    if not args.no_legend:
        order = [c[0] for c in CATEGORIES] + [OTHER[0]]
        handles = [
            Patch(facecolor=legend[label], label=label) for label in order if label in legend
        ]
        handles += [
            Line2D([], [], color=c, ls=ls, label=lab)
            for lab, c, ls, flag in (
                ("polar angle", MRAD_COLOR, "--", args.mrad),
                ("pseudorapidity", ETA_COLOR, ":", args.eta),
                (r"$|\cos\theta|$", COSTHETA_COLOR, "-.", args.costheta),
            )
            if flag
        ]
        fig.legend(
            handles=handles,
            loc="outside lower center",
            # about 1.6 inch per entry, so the legend never gets wider than the figure
            ncol=max(1, min(len(handles), int(fig.get_figwidth() / 1.6))),
            frameon=False,
            fontsize=8,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200, bbox_inches="tight", pad_inches=0.05)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
