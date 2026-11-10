"""Extract the per-event observables of the ZH -> ll + X recoil analysis from the output of
steering/llrecoil.py and store them as HDF5 items which can be read by the cutflow tool of
ILDAnaSoft/ZHH (bin/cutflow, see zhh/cli/cutflow.py). The observables themselves are computed
by extract_observables.py.

Output: for every item (a column of the cutflow data store), one HDF5 file per input file in the
layout written by the ROOT2HDF5Converter of the cutflow tool:

    <items_dir>/<tree>.<branch>/item.<i>.h5        i: index of the input file in the argument list

    ExtractObservables.<name>                     the observables listed in OBSERVABLES
    FinalStates.final_state_counts.second         std::map<int, int> final_state_counts (values only;
                                                  17 columns dim0..dim16, ordered by FS_KEYS)
    FinalStates.{event,cross_section,process,polarization_code,n_b_from_higgs}
                                                  event meta data required by the cutflow tool

With --main-file, the main HDF5 file of a cutflow source is additionally created, which links
(virtual datasets) to all items. This is required to run the cutflow tool with
--skip-integrity-check without any ROOT files; the file must be located at
<cwd of cutflow>/<hypothesis>.<source name>.h5.

Usage (key4hep sourced):
    python -m hinv.ana.extract_observables_cutflow --items-dir <items_dir> [--main-file <file.h5>]
        [--jobs N] [--processes <processes.json>] <reco.slcio> ...
    See hinv/configs/README.md for running the cutflow tool on the output.
"""

import argparse
import json
import os
import os.path as osp
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import h5py
import numpy as np

from hinv.ana.extract_observables import OBSERVABLES, event_observables

# process name (event parameter processName) -> process ID, as used by the cutflow tool
DEFAULT_PROCESSES = osp.join(osp.dirname(osp.abspath(__file__)), "../configs/processes.json")

# dtype of the HDF5 items; float32 where not listed
OBSERVABLE_DTYPES = {"pair_type": "uint8", "n_rest": "uint16", "n_isolep": "uint8"}

ITEM_TREE_OBSERVABLES = "ExtractObservables"
ITEM_TREE_FINAL_STATES = "FinalStates"

# keys (PDG ids; 1-6: quarks, 21: g, 22: gamma, 23: Z, 24: W, 25: h) of the std::map<int, int>
# m_final_state_counts of the FinalStateRecorder; std::map is sorted -> this is the column order
FS_KEYS = [1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16, 21, 22, 23, 24, 25]

# TODO: determine from MCParticlesSkimmed. for now, every event has one Higgs and two muons
FS_COUNTS_FIXED = {25: 1, 13: 2}

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

    out_dir = f"{items_dir}/{tree}.{branch}"
    os.makedirs(out_dir, exist_ok=True)

    with h5py.File(f"{out_dir}/item.{chunk_idx}.h5", "w") as hf:
        hf.attrs["chunk_idx"] = chunk_idx
        hf.attrs["tree"] = tree
        hf.attrs["branch"] = branch
        hf.attrs["input_files"] = [input_file]

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

    path = osp.abspath(path)
    reader = IOIMPL.LCFactory.getInstance().createLCReader()
    reader.open(path)
    columns = {name: [] for name in OBSERVABLES}
    event_numbers = []
    meta = None

    for event in reader:
        if meta is None:
            params = event.getParameters()

            meta = {
                "cross_section": params.getFloatVal("crossSection"),
                "process": PROCESS_IDS[params.getStringVal("processName")],
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
    for pdg, count in FS_COUNTS_FIXED.items():
        counts[:, FS_KEYS.index(pdg)] = count

    write(ITEM_TREE_FINAL_STATES, "final_state_counts.second", counts, "uint8")
    write(ITEM_TREE_FINAL_STATES, "event", event_numbers, "uint32")
    write(ITEM_TREE_FINAL_STATES, "cross_section", np.full(n_events, meta["cross_section"]), "float32")
    write(ITEM_TREE_FINAL_STATES, "process", np.full(n_events, meta["process"]), "uint32")
    write(ITEM_TREE_FINAL_STATES, "polarization_code", np.full(n_events, meta["pol_code"]), "uint8")
    write(ITEM_TREE_FINAL_STATES, "n_b_from_higgs", np.zeros(n_events), "uint8")

    n_pairs = int(np.sum(np.array(columns["pair_type"]) > 0))
    return n_events, f"{osp.basename(path)}: {n_pairs}/{n_events} events with lepton pair"


def write_main_file(main_file, items_dir, files, sizes):
    """Creates the main HDF5 file of a cutflow source: for every item a virtual dataset linking
    the chunks (same as createVDS in the ROOT2HDF5Converter), the nrows attribute and the meta
    file (<main_file without extension>.meta.json) which marks the dataset as complete."""

    nrows = int(np.sum(sizes))
    os.makedirs(osp.dirname(osp.abspath(main_file)), exist_ok=True)

    with h5py.File(main_file, "a") as hf:
        hf.attrs["nrows"] = nrows

        if "id" in hf:
            del hf["id"]
        hf["id"] = np.arange(nrows, dtype="uint32")

        for tree, branch, name, dtype in item_specs():
            chunks = [f"{items_dir}/{tree}.{branch}/item.{i}.h5" for i in range(len(files))]

            with h5py.File(chunks[0], "r") as cf:
                col_names = list(cf.attrs["col_names"])
                multi = len(cf["shape"]) > 1

            for col in col_names:
                layout = h5py.VirtualLayout((nrows,), dtype)
                start = 0
                for chunk, size in zip(chunks, sizes):
                    layout[start:start + size] = h5py.VirtualSource(chunk, col, shape=(size,), dtype=dtype)
                    start += size

                key = f"{name}.{col}" if multi else name
                if key in hf:
                    del hf[key]
                hf.create_virtual_dataset(key, layout, fillvalue=np.nan)

    with open(f"{osp.splitext(main_file)[0]}.meta.json", "wt", encoding="utf-8") as jf:
        json.dump({"files": [osp.abspath(f) for f in files], "sizes": [int(s) for s in sizes]}, jf, ensure_ascii=False, indent=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", help="Reco SLCIO files; the i-th file is stored as chunk item.<i>.h5")
    parser.add_argument("--items-dir", required=True, help="Output directory of the HDF5 items")
    parser.add_argument("--main-file", default=None, help="If given, also create the main HDF5 file of the cutflow source at this path")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel processes (default: 8)")
    parser.add_argument("--processes", default=DEFAULT_PROCESSES, help="JSON file mapping process names to IDs (default: hinv/configs/processes.json)")
    args = parser.parse_args()

    with open(args.processes) as tf:
        PROCESS_IDS: dict[str, int] = json.load(tf)

    missing = [f for f in args.files if not osp.isfile(f)]
    if missing:
        parser.error("input file(s) not found:\n  " + "\n  ".join(missing))

    items_dir = osp.abspath(args.items_dir)
    tasks = [(i, f, items_dir, PROCESS_IDS) for i, f in enumerate(args.files)]

    # spawn: fresh interpreters, so ROOT/pyLCIO are initialised per process
    sizes = []
    with ProcessPoolExecutor(max_workers=min(args.jobs, len(tasks)), mp_context=get_context("spawn")) as pool:
        for n_events, message in pool.map(process_file, tasks):
            sizes.append(n_events)
            print(message)

    if args.main_file:
        write_main_file(args.main_file, items_dir, args.files, sizes)
        print(f"Wrote main file {args.main_file} ({sum(sizes)} events)")


if __name__ == "__main__":
    main()
