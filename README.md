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
| `sgv_geometries/` | SGV geometries of ILD@FCC and ILD@ILC                                                                                 |

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
