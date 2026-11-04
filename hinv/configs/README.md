# Cutflow analysis of ZH -> ll + invisible

Steering files for the `cutflow` tool of [ILDAnaSoft/ZHH](https://github.com/ILDAnaSoft/ZHH):

| File                    | Content                                                         |
| ----------------------- | --------------------------------------------------------------- |
| `e2e2h_inv_ilc.yaml`    | ILD@ILC, 250 GeV, 2 ab^-1, P(e-, e+) = (-0.8, +0.3)             |
| `e2e2h_inv_fcc.yaml`    | ILD@FCC, 240 GeV, 2 ab^-1, unpolarised                          |
| `processes.json`        | process name (LCIO event parameter `processName`) -> process ID |
| `event_categories.yaml` | event categories, defined by process ID                         |
| `plot_options.yaml`     | plot options per quantity                                       |

Both steerings run the preselection and write cutflow plots and tables. Each one has two
sources: the signal `e2e2h` and the `zz_mumununu` background.

## 1. Create the HDF5 datasets

`hinv.ana.extract_observables_cutflow` reads reco SLCIO files (output of `hinv.reco.reco`) and
writes one cutflow source:

- `--items-dir`: the HDF5 items, one file per input file and observable
- `--main-file`: the main HDF5 file, which links all items via virtual datasets. The `cutflow`
  tool expects it at `$PWD/<hypothesis>.<source name>.h5`.

The steering files read the items from `$DATASET_ROOT/dataset_<source name>/items`. Run
everything from `$DATASET_ROOT`:

```bash
source setup.sh  # in the repository root; key4hep must be set up too
export DATASET_ROOT=/data/dust/user/$USER/hinv/cutflow
mkdir -p $DATASET_ROOT && cd $DATASET_ROOT
RECO=$dtDir/2026-10-reco/2026-10-27

# ILC: all files of both polarisations, eL.pR and eR.pL
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2h_pol/items \
    --main-file mumuH_inv.e2e2h_pol.h5 $RECO/E250-SetA.Pe2e2h_inv.*.slcio
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2vv_pol/items \
    --main-file mumuH_inv.e2e2vv_pol.h5 $RECO/E250-SetA.P4f_mumununu.*.slcio

# FCC
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2h_nopol/items \
    --main-file mumuH_inv.e2e2h_nopol.h5 $RECO/E240-FCCee_PB.Pe2e2h_inv.*.slcio
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2vv_nopol/items \
    --main-file mumuH_inv.e2e2vv_nopol.h5 $RECO/E240-FCCee_PB.P4f_mumununu.*.slcio
```

If a new process is added, register it in `processes.json` and `event_categories.yaml`;
`--processes` selects a different process file.

### Using several SLCIO files

Each call writes one source and takes any number of files, so samples split into many files work
the same way. Files are processed in parallel (`--jobs`, default 8). For example, the 20 files of
`2f_mumu` at ILC as a new source, which also needs an entry in `sources` of the steering file with
`items: [ mumu ]`:

```bash
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_mumu_pol/items \
    --main-file mumuH_inv.mumu_pol.h5 $RECO/E250-SetA.P2f_mumu.*.slcio
```

- **Pass all files of a source in one call.** Every call numbers its chunks from `item.0.h5`, so a
  second call (also via `xargs`, which may split the list) overwrites the first one instead of
  appending to it.
- **The normalisation follows the files.** For each process and polarisation, `cutflow` computes
  `weight = cross section * luminosity * w_pol / n_gen`, with `n_gen` the number of events of that
  combination in the source. More files only lower the event weights; the event yield stays the
  same.
- **Include every polarisation.** `w_pol` comes from `beam_polarization`, and a polarisation
  without files is left out without any warning. A source can contain several polarisations.
- **Put each process and polarisation in only one source.** Each source normalises to the full
  cross section by itself, so one that is split across two sources is counted twice.
- **Delete the old output before changing the files of a source**, e.g.
  `rm -rf dataset_e2e2h_pol mumuH_inv.e2e2h_pol.*`. The main file is updated in place, so the
  weights and the `.npz` file written by `cutflow` would otherwise stay as they were.
- **Do not move `$DATASET_ROOT` afterwards.** The main file links to the items by absolute path.

Each input file creates 19 HDF5 items, so N files give 19 N small files in `--items-dir`.

## 2. Run the cutflow

From the same directory, with `$DATASET_ROOT` still set:

```bash
cutflow $HINV_DIR/hinv/configs/e2e2h_inv_ilc.yaml --skip-integrity-check
cutflow $HINV_DIR/hinv/configs/e2e2h_inv_fcc.yaml --skip-integrity-check
```

`--skip-integrity-check` is required: the HDF5 data was not converted from ROOT files by the
`cutflow` tool itself, so there are no ROOT files to check it against. The files referenced in
the steering (`processes.json`, ...) are found relative to the steering file.

Outputs go to the current directory and are named `<analysis_name>_<hypothesis>_cutflow_*`, e.g.
`ILD_ILC_ZH_inv_mumuH_inv_cutflow_preselection_plots.pdf`, plus `..._table*.pdf` and
`..._table_counts.csv`. The preselection result is cached in `..._cutflow_presel.pickle`. When the
cuts change, the cache is recomputed automatically. When the data changes, delete it by hand.
