# H->Invisible & Extra Scalar Analyses

This repository contains shared code of the Higgs->Invisible and Extra Scalar analyses.

## Layout

| Path              | Content                                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------------- |
| `hinv/`           | Python package: shared `paths.py` (from `$codeDir`/`$dtDir`) and `samples.py` (sample names, collider settings, runs) |
| `hinv/sim/`       | SGV fast simulation                                                                                                   |
| `hinv/reco/`      | Lepton tagging + pairing with `k4run`                                                                                 |
| `hinv/ana/`       | Observables, weighted datasets, plots                                                                                 |
| `hinv/configs/`   | Steering files for the `cutflow` tool of ILDAnaSoft/ZHH, see [hinv/configs/README.md](hinv/configs/README.md)         |
| `hinv/workflows/` | [hep_workflows](https://github.com/nVentis/hep-workflows) plugin and configurations, see [Usage with hep-workflows](#usage-with-hep-workflows) |
| `steering/`       | Gaudi steering files (run with `k4run`, not imported)                                                                 |
| `sgv_geometries/` | SGV geometries of ILD@FCC and ILD@ILC                                                                                 |

## Usage

```bash
source setup.sh  # adds the repository to PYTHONPATH
python -m hinv.sim.sgv batch  # $dtDir/<WHIZARD_SUBDIR> -> $dtDir/<SGV_SUBDIR>
python -m hinv.reco.reco  # -> $dtDir/<RECO_SUBDIR>
python -m hinv.ana.extract_observables
python -m hinv.ana.control_plots
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

## Usage with hep-workflows

The steps of [Usage](#usage) up to the lepton pairing can also be run with [hep_workflows](https://github.com/nVentis/hep-workflows), which handles batch submission, job splitting and resubmission. This repository is a plugin of hep_workflows: once installed, its configurations are available in `law` under their tag.

### Setup

With the hep_workflows environment set up (see its README), install this repository into its Python environment:

```bash
pip install --no-deps -e .
```

The install must be editable, as the configurations use `steering/` and `sgv_geometries/` from the checkout. `--no-deps` keeps an existing editable install of hep_workflows; without it, pip may replace it with the GitHub version.

The following must be available, e.g. via the `.env` file of hep_workflows:

- `$dtDir`: the WHIZARD samples are read from `$dtDir/<WHIZARD_SUBDIR>`, see `hinv/paths.py`.
- `$codeDir`: the reco tasks load `$codeDir/ZHH/source/LeptonPairing/lib/libLeptonPairing.so`, see [Dependencies](#dependencies). It must be a recent build (one containing `LeptonPairingCombined`) for the key4hep release in use.
- `$SGV_DIR`: an SGV build for the key4hep release in use.

### Configurations

The configurations are defined in `hinv/workflows/fast_k4run.py`. They run the SGV fast simulation and `steering/llrecoil.py` on the existing WHIZARD samples, without an event generation step. The analysis tasks are not used.

| Tag                       | Detector | Samples                                | key4hep release                               |
| ------------------------- | -------- | -------------------------------------- | --------------------------------------------- |
| `250-ilc-hinv-fast-k4run` | ILD@ILC  | 250 GeV, `E250-SetA`, polarised eL.pR and eR.pL | e.g. 2025-01-28                      |
| `240-fcc-hinv-fast-k4run` | ILD@FCC  | 240 GeV, `E240-FCCee_PB`, unpolarised  | 2026-04-08 and later (must contain `ILD_FCCee_v01`) |

Both include the samples `e2e2h_inv`, `4f_mumununu`, `2f_mumu` and `4f_eemumu`. Energy, crossing angle, SGV geometry and detector model are chosen per file, as in `hinv.sim.sgv`.

### Running

Set the tag once, then run the tasks in this order:

```bash
TAG=250-ilc-hinv-fast-k4run  # or 240-fcc-hinv-fast-k4run

law run FastSimSGV --tag=$TAG        # SGV fast simulation, one output file per input file
law run RawIndex --tag=$TAG          # collects process, polarisation, cross section and events of all files
law run RecoRuntime --tag=$TAG       # runs llrecoil.py on 50 events of a few files per sample to measure the runtime
law run CreateRecoChunks --tag=$TAG  # splits the events into jobs, based on the measured runtime and maximum runtime
law run RecoFinal --tag=$TAG         # runs llrecoil.py on all chunks, i.e. lepton tagging and pairing
```

Each task runs the tasks it depends on if needed, so `law run RecoFinal --tag=$TAG` alone is enough to run the whole chain. Outputs are written to `$DATA_PATH/<task>/<tag>`, and tasks with existing outputs are not run again.

Tasks are submitted to HTCondor by default. To run on the local node instead, add `--workflow local --workers 8` to `FastSimSGV`, `RecoRuntime` and `RecoFinal`.

For a quick test with few events, run `CreateRecoChunks` with e.g. `--fraction 0.002` before `RecoFinal`. Remove the outputs of `CreateRecoChunks` and `RecoFinal` before the full run.
