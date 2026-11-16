# H->Invisible & Extra Scalar Analyses

This repository contains shared code of the Higgs->Invisible and Extra Scalar analyses.

## Layout

| Path              | Content                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------- |
| `hinv/`           | Python package: shared `paths.py` (from `$codeDir`/`$dtDir`), `samples.py` (sample names, collider settings), `runs.py` (run plans) |
| `hinv/sim/`       | SGV fast simulation                                                                                                   |
| `hinv/reco/`      | Lepton tagging + pairing with `k4run`                                                                                 |
| `hinv/ana/`       | Observables, weighted datasets, plots                                                                                 |
| `hinv/configs/`   | Steering files for the `cutflow` tool of ILDAnaSoft/ZHH, see [hinv/configs/README.md](hinv/configs/README.md)         |
| `steering/`       | Gaudi steering files (run with `k4run`, not imported)                                                                 |
| `sgv_geometries/` | SGV geometries of ILD@FCC and ILD@ILC, SGV steering for each (`sgv_ildfcc.steer`, `sgv_ild_ilc.steer`)              |
| `utils/`          | Stand-alone helpers, e.g. `plot_sgv_geometry.py` (r-z view of SGV geometries with polar-angle/eta rays)               |

## Setup

The Python environment is a `.venv` in this repository on top of key4hep. Create it once:

```bash
source setup.sh  # sets up key4hep
python -m venv --system-site-packages .venv
.venv/bin/pip install -e .
```

Afterwards, `source setup.sh` is all that is needed in a new shell. It sets up key4hep, activates the `.venv` and adds `$codeDir/ZHH` to `PYTHONPATH` for the cutflow tool.

> [!IMPORTANT]
> Do not `pip install` ZHH into this environment, and do not use a ZHH checkout which has a `zhh.egg-info` directory, as an editable install creates. `hep_workflows` then loads the plugin of ZHH when it is imported, which fails without the environment of ZHH (`No module named 'workflows'`, `KeyError: 'REPO_ROOT'`).

## Usage

```bash
source setup.sh
python -m hinv.sim.sgv batch  # $dtDir/<WHIZARD_SUBDIR> -> $dtDir/<SGV_SUBDIR>
python -m hinv.reco.reco  # -> $dtDir/<RECO_SUBDIR>
python -m hinv.ana.extract_observables
python -m hinv.ana.control_plots
python -m hinv.ana.extract_observables_cutflow  # -> $dtDir/<CUTFLOW_SUBDIR>, see hinv/configs/README.md
```

Default sub-directories are set in `hinv/paths.py`; every script has `--help`.

> [!WARNING]
> **Run SGV with each geometry only with its steering in `sgv_geometries/`** (`sgv_ildfcc.steer` for
> ILD@FCC, `sgv_ild_ilc.steer` for ILD@ILC), also outside the scripts of this repository. The
> default `$SGV_DIR/tests/sgv.steer` is written for the old DBD version of ILD@ILC: with the
> ILD@FCC and with the ILD-IDR calorimeter layers its `CALORIMETER_CODES` are shifted, so e.g.
> barrel ECal energy is written as HCAL (ILD@FCC) or endcap ECal energy as LCAL (ILD@ILC), and the
> ECal-based photon and electron identification fails.
> `python -m hinv.sim.sgv batch` selects the steering per collider; for `run`, pass `--steering`.

`hinv.sim.sgv` also sets the tracker codes per geometry (`hinv/sim/tracker_codes.py`): the
subdetector hit numbers of SGV tracks then follow the DD4hep detector IDs as in full simulation
(ILD@ILC: VXD 1, SIT 2, FTD 3, TPC 4, SET 5, ETD 6; ILD@FCC: vertex barrel 1, vertex endcap 2,
inner tracker barrel 3, TPC 4, inner tracker endcap 5, SET 6), with one TPC hit per pad row.
The `TRACKER_CODES` of the steering files fit none of the geometries, so outside these scripts the
track hit numbers are mislabelled. For `run`, pass `--detector` (e.g. `ILD_FCCee_v01`) to get the
codes. Measuring layers of one subdetector must have names that match its pattern in
`tracker_codes.py`; otherwise SGV is not started.

## Dependencies

`steering/llrecoil.py` uses the `LeptonPairingCombined` processor from [ILDAnaSoft/ZHH](https://github.com/ILDAnaSoft/ZHH) (`source/LeptonPairing`, add `lib/libLeptonPairing.so` to `MARLIN_DLL`).

## Formatting

> [!IMPORTANT]
> The following commands may require to setup the `key4hep` stack first.

Python

```bash
git ls-files -z "*.py" | xargs -0 bash -c 'ruff format --line-length 99 -v "$@"' _
```

cpp

```bash
git ls-files -z "*.C" "*.cc" "*.cpp" "*.h" "*.hpp" | xargs -0 clang-format -i
```
