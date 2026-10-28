"""Run steering/llrecoil.py (k4run) on all SGV output files of a directory.

The detector model is chosen per collider (see samples.py). Requires a sourced key4hep
stack (the one SGV and LeptonPairing were built with).

Usage:
    python -m hinv.reco.reco [<sgv_dir>] [<output_dir>] [--jobs N] [--ild-fcc-version {1,2}]
        [--n-events N]
    Directories default to $dtDir/<SGV_SUBDIR> and $dtDir/<RECO_SUBDIR> (see paths.py).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hinv.paths import RECO_SUBDIR, SGV_SUBDIR, data_dir, lepton_pairing_lib
from hinv.samples import collider_settings, parse_sample

STEERING = Path(__file__).resolve().parents[2] / "steering/llrecoil.py"


def run_reco(
    input_file: Path, output_base: Path, detector_model: str, n_events: int, env: dict
) -> bool:
    """Runs the steering on one file; writes <output_base>.slcio/.log/_LeptonPairing.root."""
    # sample names contain dots, so append extensions instead of using with_suffix
    log = Path(f"{output_base}.log")
    # separate work dirs: Marlin writes cdb.log etc. into the CWD
    work = Path(tempfile.mkdtemp(prefix="TMP-reco-", dir=output_base.parent))

    with open(log, "w") as stream:
        result = subprocess.run(
            [
                "k4run",
                str(STEERING),
                "--inputFiles",
                str(input_file),
                "--outputBase",
                str(output_base),
                "--detectorModel",
                detector_model,
                "--nEvents",
                str(n_events),
            ],
            cwd=work,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            check=False,  # failures are reported via returncode below
        )

    if result.returncode != 0 or not Path(f"{output_base}.slcio").exists():
        print(
            f"Reco failed for {input_file.name} (exit code {result.returncode}), see {log}",
            file=sys.stderr,
        )
        return False

    shutil.rmtree(work)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sgv_dir", type=Path, nargs="?", help=f"Default: $dtDir/{SGV_SUBDIR}")
    parser.add_argument("output_dir", type=Path, nargs="?", help=f"Default: $dtDir/{RECO_SUBDIR}")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel jobs (default: 8)")
    parser.add_argument("--ild-fcc-version", type=int, choices=(1, 2), default=1)
    parser.add_argument("--n-events", type=int, default=-1, help="Default: all events")
    args = parser.parse_args()

    if "KEY4HEP_STACK" not in os.environ or shutil.which("k4run") is None:
        sys.exit("key4hep is not set up: source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08")
    lib = lepton_pairing_lib()
    if not lib.is_file():
        sys.exit(f"LeptonPairing library not found: {lib}")

    env = {**os.environ, "MARLIN_DLL": f"{lib}:{os.environ.get('MARLIN_DLL', '')}"}

    sgv_dir = (args.sgv_dir or data_dir() / SGV_SUBDIR).resolve()
    inputs = sorted(sgv_dir.glob("*.slcio"))
    if not inputs:
        sys.exit(f"No .slcio files found in {sgv_dir}")
    output_dir = (args.output_dir or data_dir() / RECO_SUBDIR).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {}
        for f in inputs:
            try:
                settings = collider_settings(parse_sample(f), args.ild_fcc_version)
            except ValueError as e:
                print(f"Skipping {f.name}: {e}")
                continue

            print(f"{f.name}: {settings.detector_model}")
            futures[f.name] = executor.submit(
                run_reco,
                f,
                output_dir / f.stem,
                settings.detector_model,
                args.n_events,
                env,
            )

    failed = [name for name, future in futures.items() if not future.result()]
    if failed:
        print("Failed jobs:\n  " + "\n  ".join(failed), file=sys.stderr)
        return 1
    print(f"All {len(futures)} reco jobs done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
