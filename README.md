# H->Invisible & Extra Scalar Analyses

This repository contains shared code of the Higgs->Invisible and Extra Scalar analyses.

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
