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
| `sgv_geometries/` | SGV geometries of ILD@FCC and ILD@ILC, SGV steering for ILD@FCC (`sgv_ildfcc.steer`)                                  |
| `utils/`          | Stand-alone helpers, e.g. `plot_sgv_geometry.py` (r-z view of SGV geometries with polar-angle/eta rays)               |

## Usage

```bash
source setup.sh  # adds the repository to PYTHONPATH
python -m hinv.sim.sgv batch  # $dtDir/<WHIZARD_SUBDIR> -> $dtDir/<SGV_SUBDIR>
python -m hinv.reco.reco  # -> $dtDir/<RECO_SUBDIR>
python -m hinv.ana.extract_observables
python -m hinv.ana.control_plots
python -m hinv.ana.extract_observables_cutflow  # -> $dtDir/<CUTFLOW_SUBDIR>, see hinv/configs/README.md
```

Default sub-directories are set in `hinv/paths.py`; every script has `--help`.

> [!WARNING]
> **Run SGV with the ILD@FCC geometries only with `sgv_geometries/sgv_ildfcc.steer`**, also outside
> the scripts of this repository. The default `$SGV_DIR/tests/sgv.steer` is written for ILD@ILC:
> with the ILD@FCC calorimeter layers its `CALORIMETER_CODES` are shifted, so barrel ECal energy is
> written as HCAL and the ECal-based photon and electron identification fails.
> `python -m hinv.sim.sgv batch` selects the steering per collider; for `run`, pass
> `--steering sgv_geometries/sgv_ildfcc.steer`.

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
