# Cutflow analysis of ZH -> ll + invisible

Steering files for the `cutflow` tool of [ILDAnaSoft/ZHH](https://github.com/ILDAnaSoft/ZHH), one per
run of `RUNS` in `hinv/runs.py`, which reads the energy, luminosity and polarisation from these files:

| File                       | Run                                                     |
| -------------------------- | ------------------------------------------------------- |
| `e2e2h_inv_ilc250_lr.yaml` | ILD@ILC, 250 GeV, 0.9 ab^-1, P(e-, e+) = (-0.8, +0.3)   |
| `e2e2h_inv_ilc250_rl.yaml` | ILD@ILC, 250 GeV, 0.9 ab^-1, P(e-, e+) = (+0.8, -0.3)   |
| `e2e2h_inv_fcc240.yaml`    | ILD@FCC, 240 GeV, 10.8 ab^-1, unpolarised               |

They share the following files, which are found relative to the steering file:

| File                                | Content                                                         |
| ----------------------------------- | --------------------------------------------------------------- |
| `cuts.yaml`                         | selection, not yet optimised                                    |
| `sources_ilc.yaml`, `sources_fcc.yaml` | sources per collider: signal and the three backgrounds       |
| `cutflow_table.yaml`                | rows of the cutflow table                                       |
| `processes.json`                    | process name (LCIO event parameter `processName`) -> process ID |
| `event_categories.yaml`             | event categories, defined by process ID                         |
| `plot_options.yaml`                 | plot options per quantity                                       |

## Requirements

A ZHH checkout at `$codeDir/ZHH` from `main` (at least #23, which is needed for the process IDs used
here), and the environment described under Setup in the [main README](../../README.md).

## 1. Create the HDF5 datasets

```bash
source setup.sh  # in the repository root
python -m hinv.ana.extract_observables_cutflow  # $dtDir/<RECO_SUBDIR> -> $dtDir/<CUTFLOW_SUBDIR>
```

This reads all reco SLCIO files of all runs and writes:

- `dataset_<collider>_<source>/items/`: the HDF5 items, 19 per input file. The runs of a collider
  share them.
- `mumuH_inv_<run>.<source>.h5`: the main HDF5 files, one per run and source, which link all items
  via virtual datasets. The `cutflow` tool reads them from the current directory, and they hold the
  weights of a run. They link to the items by absolute path, so do not move the directory afterwards.

The extraction stops if a process or polarisation of a run has no files, as `cutflow` would leave
it out of the normalisation without a warning. For each process and polarisation, `cutflow` computes
`weight = cross section * luminosity * w_pol / n_gen`, with `n_gen` the number of events in the
source, so more files only lower the event weights. To add a process, register it in `SOURCES` and
`FS_COUNTS` of the script, `processes.json`, `event_categories.yaml`, `sources_*.yaml` and
`cutflow_table.yaml`.

Rerunning the extraction recreates the main files and removes the `cutflow` outputs of these runs.

## 2. Run the cutflow

```bash
cd $dtDir/2026-10-cutflow/2026-10-27  # see CUTFLOW_SUBDIR in hinv/paths.py
export DATASET_ROOT=$PWD

python -m zhh.cli.cutflow $HINV_DIR/hinv/configs/e2e2h_inv_ilc250_lr.yaml --skip-integrity-check
python -m zhh.cli.cutflow $HINV_DIR/hinv/configs/e2e2h_inv_ilc250_rl.yaml --skip-integrity-check
python -m zhh.cli.cutflow $HINV_DIR/hinv/configs/e2e2h_inv_fcc240.yaml --skip-integrity-check
```

`--skip-integrity-check` is required: the HDF5 data was not converted from ROOT files by the
`cutflow` tool itself, so there are no ROOT files to check it against.

Outputs go to the current directory and are named `ILD_ZH_inv_mumuH_inv_<run>_cutflow_*`, e.g.
`..._preselection_plots.pdf`, plus `..._table*.pdf` and `..._table_counts.csv`.

**Add `--reset` after changing a steering file**, e.g. the cuts. Without it, `cutflow` skips every
action whose output file exists, so plots and tables silently stay as they were.

The LR and RL runs are separate cutflows, and each one contains both helicity samples with the
weights of its polarisation. The tool does not combine them, and its tables do not show the MC
statistical uncertainty.
