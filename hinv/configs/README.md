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

# ILC
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2h_pol/items \
    --main-file mumuH_inv.e2e2h_pol.h5 $RECO/E250-SetA.Pe2e2h_inv.Gwhizard-3_1_5.eR.pL.I403001.0.slcio
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2vv_pol/items \
    --main-file mumuH_inv.e2e2vv_pol.h5 $RECO/E250-SetA.P4f_mumununu.Gwhizard-3_1_5.eL.pR.I403002.0.slcio

# FCC
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2h_nopol/items \
    --main-file mumuH_inv.e2e2h_nopol.h5 $RECO/E240-FCCee_PB.Pe2e2h_inv.Gwhizard-3_1_5.eU.pU.I403001.0.slcio
python -m hinv.ana.extract_observables_cutflow --items-dir dataset_e2e2vv_nopol/items \
    --main-file mumuH_inv.e2e2vv_nopol.h5 $RECO/E240-FCCee_PB.P4f_mumununu.Gwhizard-3_1_5.eU.pU.I403002.0.slcio
```

Each call can take several SLCIO files of the same source. Files are processed in parallel
(`--jobs`, default 8). If a new process is added, register it in `processes.json` and
`event_categories.yaml`; `--processes` selects a different process file.

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
