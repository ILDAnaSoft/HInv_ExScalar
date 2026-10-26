# H->Invisible & Extra Scalar Analyses

This repository contains shared code of the Higgs->Invisible and Extra Scalar analyses.

## Dependencies

`scripts/steering_llrecoil.py` uses the `LeptonPairingCombined` processor from [ILDAnaSoft/ZHH](https://github.com/ILDAnaSoft/ZHH) (`source/LeptonPairing`, add `lib/libLeptonPairing.so` to `MARLIN_DLL`).

> [!WARNING]
> Until the ZHH branches `fix/leptonpairingcombined` and `fix/leptonpairing-defaults` are merged, build `libLeptonPairing.so` from a branch containing both (locally: `hinv/local`). Afterwards, rebuild from ZHH `main` and remove this note.

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
