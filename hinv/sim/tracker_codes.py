"""SGV tracker codes: label the SGV tracking layers with the subdetector numbers of full simulation.

SGV (tests/usesgvlcio.F95) walks its tracking layers sorted by radius (barrel) and then by z
(forward), skipping calorimeter material, and starts a new group whenever the layer name changes.
analysis_steering.TRACKER_CODES gives the number of groups, then one code per group, by position.
A track's subdetector hit numbers get, for code c, the entries 2c-2 and 2c-1 (hits in the fit, all
hits), counting TRACKER_NDF_PER_LAYER(c) / 2 hits per SGV layer.

Full simulation (MarlinTrk::addHitNumbersToTrack) fills the same entries from the system field of
the hit cell IDs, i.e. the DD4hep detector IDs. So the codes are those IDs:
    ILD@ILC (lcio::ILDDetID): VXD 1, SIT 2, FTD 3, TPC 4, SET 5, ETD 6
    ILD@FCC (k4geo ILD_common_FCCee/basic_defs.xml): vertex barrel 1, vertex endcap 2,
        inner tracker barrel 3, TPC 4, inner tracker endcap 5, SET 6
The ILD@ILC default steering of SGV uses FTD 2, SIT 3 instead, and its list of codes was written
for an older layer order, so it is replaced for every geometry.

The group order depends on SGV's sort (an unstable quicksort, so layers of different names at the
same radius or z come out in an order that is hard to predict), so the groups are taken from the
table SGV prints at start-up, see hinv.sim.sgv.tracker_options.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# SGV keeps 14 characters of a layer name
NAME_LENGTH = 14
# steer(4, 0:100) in za_process.F95 holds 20 fixed entries, then the tracker codes, the
# calorimeter codes and the ndf per tracker code
STEER_SIZE = 100
STEER_FIXED = 20


@dataclass(frozen=True)
class TrackerScheme:
    """Layer-name patterns (full match, first match wins) -> code; pad rows of the TPC."""

    patterns: tuple[tuple[str, int], ...]
    tpc_code: int
    tpc_pad_rows: int


ILD_ILC_PATTERNS = (
    (r"VXD\d+", 1),
    (r"SIT\d+", 2),
    (r"FTD", 3),
    (r"TPC", 4),
    (r"SET", 5),
    (r"ETD", 6),
)
ILD_FCC_PATTERNS = (
    (r"VXD\d+", 1),
    (r"VXDENDCAP\d*", 2),
    (r"SIT\d+", 3),
    (r"TPC", 4),
    (r"SITENDCAP\d+", 5),
    (r"SET", 6),
)

# key: full-sim detector model (ColliderSettings.detector_model, --detector of hinv.sim.sgv run);
# TPC pad rows from the FixedPadSizeTPCData of the model (maxRow)
SCHEMES = {
    "ILD_l5_o1_v02": TrackerScheme(ILD_ILC_PATTERNS, tpc_code=4, tpc_pad_rows=220),
    "ILD_l5_v02": TrackerScheme(ILD_ILC_PATTERNS, tpc_code=4, tpc_pad_rows=220),
    "ILD_FCCee_v01": TrackerScheme(ILD_FCC_PATTERNS, tpc_code=4, tpc_pad_rows=214),
    "ILD_FCCee_v02": TrackerScheme(ILD_FCC_PATTERNS, tpc_code=4, tpc_pad_rows=158),
}

TRACKING_SECTIONS = ("BARREL_TRACKING", "FORWARD_TRACKING")
GROUP_LINE = re.compile(r"^\s+(\d+)\s+(\S+)\s+(-?\d+)(?:\s+\S+)?\s*$")
KEYWORD = re.compile(r"^\s*([A-Za-z_]+)\s*:(.*)$")


@dataclass(frozen=True)
class LayerGroups:
    tracking: tuple[str, ...]
    calorimeter: tuple[str, ...]


def parse_layer_groups(log: str) -> LayerGroups:
    """Tracking and calorimeter layer groups from the table SGV prints at start-up
    ("number name code [name]", numbered from 1 for the tracking and again for the calorimeter
    groups)."""
    runs: list[list[str]] = []
    for line in log.splitlines():
        match = GROUP_LINE.match(line)
        if not match:
            continue
        number, name = int(match.group(1)), match.group(2)
        if number == 1:
            if len(runs) == 2:
                break
            runs.append([])
        elif not runs or number != len(runs[-1]) + 1:
            continue  # not part of the table
        runs[-1].append(name)
    if len(runs) != 2:
        raise ValueError("SGV layer-group table not found in the SGV output")
    return LayerGroups(tuple(runs[0]), tuple(runs[1]))


def measuring_layers(geometry: str) -> dict[str, int]:
    """Number of measuring (CODE 1 or 2) tracking layers per layer name of an SGV geometry.

    Follows the SGV conventions: lines starting with C, c, * or ! are comments, a LAYER record
    without a name continues the previous name, REPEAT multiplies the layer.
    """
    counts: dict[str, int] = {}
    section = name = None
    layer: dict | None = None

    def finish():
        if layer and section in TRACKING_SECTIONS and layer["code"] in (1, 2):
            counts[layer["name"]] = counts.get(layer["name"], 0) + layer["times"]

    for line in geometry.splitlines():
        if not line.strip() or line[0] in "Cc*!":
            continue
        match = KEYWORD.match(line)
        if not match:
            continue
        keyword, rest = match.group(1).upper(), match.group(2)
        if keyword == "TYPE":
            finish()
            layer, section = None, rest.strip().upper()
        elif keyword == "LAYER":
            finish()
            name = rest.strip()[:NAME_LENGTH] or name
            layer = {"name": name, "code": 0, "times": 1}
        elif layer is not None and keyword == "REPEAT":
            times = re.search(r"TIMES\s*=\s*(\d+)", rest, re.IGNORECASE)
            layer["times"] = int(times.group(1)) if times else 1
        elif layer is not None and keyword == "MEASUREMENT":
            code = re.search(r"CODE\s*=\s*(\d+)", rest, re.IGNORECASE)
            if code:
                layer["code"] = int(code.group(1))
    finish()
    return counts


def calorimeter_code_count(steering: str) -> int | None:
    """The count given in the active CALORIMETER_CODES line of the steering, if any."""
    match = re.search(r"^\s*CALORIMETER_CODES\s*=\s*(\d+)", steering, re.MULTILINE)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class TrackerCodes:
    groups: tuple[str, ...]
    codes: tuple[int, ...]  # one per group
    ndf_per_layer: tuple[int, ...]  # one per code 1..max(codes)

    def steering_options(self) -> dict:
        """Options for hinv.sim.sgv_steering.merge_options."""
        return {
            "analysis_steering.TRACKER_CODES": [len(self.codes), *self.codes],
            "analysis_steering.TRACKER_NDF_PER_LAYER": list(self.ndf_per_layer),
        }

    def summary(self) -> str:
        labelled = [f"{g}={c}" for g, c in zip(self.groups, self.codes) if c]
        return (
            f"{len(self.groups)} tracking layer groups, labelled: {' '.join(labelled)}; "
            f"ndf per layer by code: {' '.join(map(str, self.ndf_per_layer))}"
        )


def tracker_codes(
    groups: LayerGroups, geometry: Path, steering: Path, detector: str
) -> TrackerCodes:
    """Codes for SGV's tracking-layer groups of the given full-sim detector model.

    Raises ValueError if a measuring layer has no code, a passive layer gets one, the steering's
    calorimeter codes don't match the calorimeter groups, or the lists overflow SGV's steering
    array.
    """
    if detector not in SCHEMES:
        raise ValueError(f"No tracker codes for detector {detector!r}, known: {sorted(SCHEMES)}")
    scheme = SCHEMES[detector]

    def code_of(name: str) -> int:
        for pattern, code in scheme.patterns:
            if re.fullmatch(pattern, name):
                return code
        return 0

    codes = tuple(code_of(g) for g in groups.tracking)
    measuring = measuring_layers(geometry.read_text())
    labelled = {g for g, c in zip(groups.tracking, codes) if c}
    problems = []
    if missing := sorted(set(measuring) - labelled):
        problems.append(f"measuring layers without a code: {', '.join(missing)}")
    if passive := sorted(labelled - set(measuring)):
        problems.append(f"passive layers with a code: {', '.join(passive)}")
    if unknown := sorted(set(measuring) - set(groups.tracking)):
        problems.append(f"measuring layers not in SGV's layer table: {', '.join(unknown)}")

    tpc_layers = sum(n for g, n in measuring.items() if code_of(g) == scheme.tpc_code)
    if not tpc_layers:
        problems.append("no measuring TPC layers")
    max_code = max(codes, default=0)
    ndf = [2] * max_code
    if tpc_layers and scheme.tpc_code <= max_code:
        # SGV counts layers * ndf / 2 hits, so a layer stands for pad_rows / layers rows
        ndf[scheme.tpc_code - 1] = round(2 * scheme.tpc_pad_rows / tpc_layers)

    n_calo = calorimeter_code_count(steering.read_text())
    if n_calo is not None and n_calo not in (0, len(groups.calorimeter)):
        problems.append(
            f"{steering.name} gives {n_calo} calorimeter codes, the geometry has "
            f"{len(groups.calorimeter)} calorimeter layer groups ({', '.join(groups.calorimeter)})"
        )
    used = STEER_FIXED + len(codes) + (n_calo or 0) + max_code
    if used > STEER_SIZE:
        problems.append(
            f"tracker codes, calorimeter codes and ndf need {used} steering entries, SGV has "
            f"{STEER_SIZE}: give layers of one subdetector the same name"
        )
    if problems:
        raise ValueError(f"{geometry.name} ({detector}): " + "; ".join(problems))
    return TrackerCodes(groups.tracking, codes, tuple(ndf))
