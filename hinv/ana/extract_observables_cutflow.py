"""Extract the per-event observables of the ZH -> ll + X recoil analysis from the output of
steering/llrecoil.py and store them as HDF5 items which can be read by the cutflow tool of
ILDAnaSoft/ZHH (bin/cutflow, see zhh/cli/cutflow.py). The observables themselves are computed
by extract_observables.py.

Output below <output_dir>, for all runs of samples.RUNS:

1. The items: for every item (a column of the cutflow data store), one HDF5 file per input file in
   the layout written by the ROOT2HDF5Converter of the cutflow tool. A source holds all
   polarisations of a process at a collider, so the runs of a collider share the items:

    dataset_<collider>_<source>/items/<tree>.<branch>/item.<i>.h5

    ExtractObservables.<name>                     the observables listed in OBSERVABLES
    FinalStates.final_state_counts.second         std::map<int, int> final_state_counts (values only;
                                                  17 columns dim0..dim16, ordered by FS_KEYS)
    FinalStates.{event,cross_section,process,polarization_code,n_b_from_higgs}
                                                  event meta data required by the cutflow tool

2. The main HDF5 files, one per run and source, which link (virtual datasets) to all items. They
   are required to run the cutflow tool with --skip-integrity-check without any ROOT files, and
   store the weights of a run, i.e. its polarisation and luminosity:

    <hypothesis>.<source>.h5    with the hypothesis mumuH_inv_<run>, e.g. mumuH_inv_ILC250_LR

Rerunning recreates the main files and removes the outputs of the cutflow tool derived from them.

Usage (key4hep sourced):
    python -m hinv.ana.extract_observables_cutflow [reco_dir] [output_dir] [--jobs N]
        [--processes <processes.json>]
    See hinv/configs/README.md for running the cutflow tool on the output.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import get_context
from pathlib import Path

import h5py
import numpy as np

from hinv.ana.extract_observables import OBSERVABLES, event_observables
from hinv.paths import CUTFLOW_SUBDIR, RECO_SUBDIR, data_dir
from hinv.samples import FCCEE, ILC, RUNS, parse_sample

# process name (event parameter processName) -> process ID, as used by the cutflow tool
DEFAULT_PROCESSES = Path(__file__).resolve().parent.parent / "configs/processes.json"

HYPOTHESIS = "mumuH_inv"

# sample process -> cutflow source; the names are used in hinv/configs/sources_<collider>.yaml
SOURCES = {"e2e2h_inv": "e2e2h", "4f_mumununu": "e2e2vv", "2f_mumu": "mumu", "4f_eemumu": "eemumu"}
COLLIDER_TAGS = {ILC: "ilc", FCCEE: "fcc"}

# dtype of the HDF5 items; float32 where not listed
OBSERVABLE_DTYPES = {"pair_type": "uint8", "n_rest": "uint16", "n_isolep": "uint8"}

ITEM_TREE_OBSERVABLES = "ExtractObservables"
ITEM_TREE_FINAL_STATES = "FinalStates"

# keys (PDG ids; 1-6: quarks, 21: g, 22: gamma, 23: Z, 24: W, 25: h) of the std::map<int, int>
# m_final_state_counts of the FinalStateRecorder; std::map is sorted -> this is the column order
FS_KEYS = [1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16, 21, 22, 23, 24, 25]

# Final state per process name; only the charged leptons and the Higgs are filled, as the neutrino
# flavours of zz_mumununu are not known per event. The event categories in event_categories.yaml
# use the process ID, so the FinalStateDefinitions of ZHH must not be used on these counts.
FS_COUNTS = {
    "e2e2h": {25: 1, 13: 2},
    "zz_mumununu": {13: 2},
    "mumu": {13: 2},
    "eemumu": {11: 2, 13: 2},
}

# polarization_code as in zhh/processes/PolarizationCodes.py: 0=eL.pL, 1=eL.pR, 2=eR.pL, 3=eR.pR, 4=unpolarized
def polarization_code(pol_em, pol_ep):
    if abs(pol_em) == 1 and abs(pol_ep) == 1:
        return 2 * (pol_em > 0) + (pol_ep > 0)
    else:
        return 4


# (tree, branch, name of the column in the main HDF5 file, dtype)
def item_specs():
    specs = [(ITEM_TREE_OBSERVABLES, name, name, OBSERVABLE_DTYPES.get(name, "float32")) for name in OBSERVABLES]
    return specs + [
        (ITEM_TREE_FINAL_STATES, "event", "event", "uint32"),
        (ITEM_TREE_FINAL_STATES, "cross_section", "cross_section", "float32"),
        (ITEM_TREE_FINAL_STATES, "final_state_counts.second", "final_state_counts", "uint8"),
        (ITEM_TREE_FINAL_STATES, "n_b_from_higgs", "n_b_from_higgs", "uint8"),
        (ITEM_TREE_FINAL_STATES, "polarization_code", "pol_code", "uint8"),
        (ITEM_TREE_FINAL_STATES, "process", "process", "uint32"),
    ]


def write_item(items_dir, tree, branch, chunk_idx, data, dtype, input_file):
    """Writes one chunk of an item in the layout of the ROOT2HDF5Converter: one dataset dim<i>
    per column, plus 'shape' and the attributes checked by the cutflow tool."""

    data = np.asarray(data)
    columns = data.reshape(len(data), -1)
    col_names = [f"dim{i}" for i in range(columns.shape[1])]

    out_dir = items_dir / f"{tree}.{branch}"
    out_dir.mkdir(parents=True, exist_ok=True)

    with h5py.File(out_dir / f"item.{chunk_idx}.h5", "w") as hf:
        hf.attrs["chunk_idx"] = chunk_idx
        hf.attrs["tree"] = tree
        hf.attrs["branch"] = branch
        hf.attrs["input_files"] = [str(input_file)]

        for i, col in enumerate(col_names):
            hf.create_dataset(col, data=columns[:, i].astype(dtype))

        # the converter leaves the number of columns at 0 for multi-column items
        hf["shape"] = np.array([len(data), 0] if data.ndim > 1 else [len(data)], dtype=int)
        hf.attrs["col_names"] = col_names
        hf.attrs["save_columnwise"] = True
        hf.attrs["dtype"] = str(np.dtype(dtype))


def process_file(args):
    try:
        return _process_file(args)
    except Exception as e:
        # cppyy exceptions/objects must not be pickled back to the parent: unpickling them there
        # imports ROOT in the result handler thread and segfaults. Pass only the message.
        raise RuntimeError(f"{args[1]}: {type(e).__name__}: {e}") from None


def _process_file(args):
    chunk_idx, path, items_dir, PROCESS_IDS = args
    from pyLCIO import IOIMPL  # imported per worker process

    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(str(path))
    columns = {name: [] for name in OBSERVABLES}
    event_numbers = []
    meta = None

    for event in reader:
        if meta is None:
            params = event.getParameters()
            process_name = params.getStringVal("processName")

            meta = {
                "cross_section": params.getFloatVal("crossSection"),
                "process": PROCESS_IDS[process_name],
                "fs_counts": FS_COUNTS[process_name],
                "pol_code": polarization_code(params.getFloatVal("beamPol1"), params.getFloatVal("beamPol2")),
            }
        event_numbers.append(event.getEventNumber())
        for name, value in event_observables(event).items():
            columns[name].append(value)
    reader.close()

    n_events = len(event_numbers)
    assert meta is not None and n_events > 0, f"no events in {path}"

    def write(tree, branch, data, dtype):
        write_item(items_dir, tree, branch, chunk_idx, data, dtype, path)

    for name, values in columns.items():
        write(ITEM_TREE_OBSERVABLES, name, values, OBSERVABLE_DTYPES.get(name, "float32"))

    counts = np.zeros((n_events, len(FS_KEYS)), dtype="uint8")
    for pdg, count in meta["fs_counts"].items():
        counts[:, FS_KEYS.index(pdg)] = count

    write(ITEM_TREE_FINAL_STATES, "final_state_counts.second", counts, "uint8")
    write(ITEM_TREE_FINAL_STATES, "event", event_numbers, "uint32")
    write(ITEM_TREE_FINAL_STATES, "cross_section", np.full(n_events, meta["cross_section"]), "float32")
    write(ITEM_TREE_FINAL_STATES, "process", np.full(n_events, meta["process"]), "uint32")
    write(ITEM_TREE_FINAL_STATES, "polarization_code", np.full(n_events, meta["pol_code"]), "uint8")
    write(ITEM_TREE_FINAL_STATES, "n_b_from_higgs", np.zeros(n_events), "uint8")

    n_pairs = int(np.sum(np.array(columns["pair_type"]) > 0))
    return n_events, f"{path.name}: {n_pairs}/{n_events} events with lepton pair"


def write_main_file(main_file, items_dir, files, sizes):
    """Creates the main HDF5 file of a cutflow source: for every item a virtual dataset linking
    the chunks (same as createVDS in the ROOT2HDF5Converter), the nrows attribute and the meta
    file (<main_file without extension>.meta.json) which marks the dataset as complete. Any older
    main file is replaced and the outputs of the cutflow tool derived from it are removed: the tool
    would otherwise keep using the old weights and selection and skip existing plots and tables."""

    nrows = int(np.sum(sizes))
    main_file.parent.mkdir(parents=True, exist_ok=True)

    hypothesis = main_file.name.split(".")[0]
    for stale in [main_file.with_suffix(".npz"), *main_file.parent.glob(f"*_{hypothesis}_cutflow_*")]:
        if stale.is_file():
            stale.unlink()

    with h5py.File(main_file, "w") as hf:
        hf.attrs["nrows"] = nrows
        hf["id"] = np.arange(nrows, dtype="uint32")

        for tree, branch, name, dtype in item_specs():
            chunks = [items_dir / f"{tree}.{branch}/item.{i}.h5" for i in range(len(files))]

            with h5py.File(chunks[0], "r") as cf:
                col_names = list(cf.attrs["col_names"])
                multi = len(cf["shape"]) > 1

            for col in col_names:
                layout = h5py.VirtualLayout((nrows,), dtype)
                start = 0
                for chunk, size in zip(chunks, sizes):
                    layout[start:start + size] = h5py.VirtualSource(str(chunk), col, shape=(size,), dtype=dtype)
                    start += size

                key = f"{name}.{col}" if multi else name
                hf.create_virtual_dataset(key, layout, fillvalue=np.nan)

    meta = {"files": [str(f) for f in files], "sizes": [int(s) for s in sizes]}
    main_file.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=4), encoding="utf-8")


@dataclass
class Source:
    """All files of a process at a collider, and the main file of each run using them."""

    items_dir: Path
    files: list[Path]
    main_files: list[Path] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)


def plan_sources(reco_dir: Path, output_dir: Path) -> dict[tuple[str, str], Source]:
    """Assigns the reco files to the sources of all runs. A process or polarisation missing from a
    run is an error: the cutflow tool would leave it out of the normalisation without any warning."""
    samples = [(f.resolve(), parse_sample(f)) for f in sorted(reco_dir.glob("*.slcio"))]

    sources = {}
    for run_key, run in RUNS.items():
        for process, source_name in SOURCES.items():
            files = {
                polarisation: [
                    f
                    for f, s in samples
                    if (s.collider, s.energy, s.isr, s.process, s.polarisation)
                    == (run.collider, run.energy, True, process, polarisation)
                ]
                for polarisation in run.polarisations()
            }
            missing = [polarisation for polarisation, found in files.items() if not found]
            if missing:
                raise SystemExit(f"Error: no {process} files for {run_key} {missing} in {reco_dir}")

            tag = COLLIDER_TAGS[run.collider]
            source = sources.setdefault(
                (tag, source_name),
                Source(
                    items_dir=output_dir / f"dataset_{tag}_{source_name}/items",
                    files=[f for found in files.values() for f in found],
                ),
            )
            source.main_files.append(output_dir / f"{HYPOTHESIS}_{run_key}.{source_name}.h5")
    return sources


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("reco_dir", type=Path, nargs="?", help=f"Default: $dtDir/{RECO_SUBDIR}")
    parser.add_argument("output_dir", type=Path, nargs="?", help=f"Default: $dtDir/{CUTFLOW_SUBDIR}")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel processes (default: 8)")
    parser.add_argument("--processes", type=Path, default=DEFAULT_PROCESSES, help="JSON file mapping process names to IDs (default: hinv/configs/processes.json)")
    args = parser.parse_args()

    reco_dir = args.reco_dir or data_dir() / RECO_SUBDIR
    output_dir = (args.output_dir or data_dir() / CUTFLOW_SUBDIR).resolve()

    PROCESS_IDS: dict[str, int] = json.loads(args.processes.read_text())

    sources = list(plan_sources(reco_dir, output_dir).values())
    tasks = [(i, f, s.items_dir, PROCESS_IDS) for s in sources for i, f in enumerate(s.files)]
    owners = [s for s in sources for _ in s.files]

    # spawn: fresh interpreters, so ROOT/pyLCIO are initialised per process
    with ProcessPoolExecutor(max_workers=min(args.jobs, len(tasks)), mp_context=get_context("spawn")) as pool:
        for source, (n_events, message) in zip(owners, pool.map(process_file, tasks)):
            source.sizes.append(n_events)
            print(message)

    for source in sources:
        for main_file in source.main_files:
            write_main_file(main_file, source.items_dir, source.files, source.sizes)
            print(f"Wrote main file {main_file} ({sum(source.sizes)} events)")


if __name__ == "__main__":
    main()
