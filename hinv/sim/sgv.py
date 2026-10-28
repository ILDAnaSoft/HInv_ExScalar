"""Run SGV fast simulation (usesgvlcio.exe) on LCIO/STDHEP generator files.

Single file, settings given explicitly:
    python -m hinv.sim.sgv run <input> <geometry.inp> <output.slcio> [--max-events N]
        [--cms-energy E] [--crossing-angle A] [--detector NAME] [--steering FILE]

All files of a directory, settings chosen per collider (see samples.py):
    python -m hinv.sim.sgv batch [<input_dir>] [<output_dir>] [--jobs N] [--ild-fcc-version {1,2}]
        [--max-events N] [--steering FILE]
    Directories default to $dtDir/<WHIZARD_SUBDIR> and $dtDir/<SGV_SUBDIR> (see paths.py).

Each job runs in its own work directory next to the output, because SGV reads and writes
fixed file names in its CWD. The environment (key4hep, sgvenv.sh) is set up by run_sgv.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path

from hinv.paths import SGV_SUBDIR, WHIZARD_SUBDIR, data_dir, sgv_dir
from hinv.samples import collider_settings, parse_sample
from hinv.sim.sgv_steering import merge_options

RUN_SGV = Path(__file__).resolve().parent / "run_sgv"
SGV_OUTPUT = "sgvout.slcio"  # set via analysis_steering.FILENAME

# input extension -> (GENERATOR_INPUT_TYPE, name of the link SGV reads)
INPUT_TYPES = {
    ".slcio": ("LCIO", "input.slcio"),
    ".lcio": ("LCIO", "input.slcio"),
    ".stdhep": ("STDH", "input.stdhep"),
}


def steering_options(
    max_events: int | None = None,
    cms_energy: float | None = None,
    crossing_angle: float | None = None,
    detector: str | None = None,
) -> dict:
    """Optional overrides in the "section.KEY" format of sgv_steering.merge_options."""
    options = {
        "global_steering.MAXEV": max_events,
        "global_generation_steering.CMS_ENE": cms_energy,
        "global_generation_steering.CROSSING_ANGLE": crossing_angle,
        "analysis_steering.DETECTOR": detector,
    }
    return {key: value for key, value in options.items() if value is not None}


def prepare_workdir(
    work: Path, input_file: Path, geometry: Path, steering: Path, options: dict
) -> None:
    generator_type, input_link = INPUT_TYPES[input_file.suffix]

    shutil.copytree(sgv_dir() / "tests", work, symlinks=True, dirs_exist_ok=True)

    # replace symlinks copied from tests/ so the originals are never touched
    for name in ("fort.17", "fort.51", "input.slcio", "input.stdhep", SGV_OUTPUT):
        (work / name).unlink(missing_ok=True)
    (work / "fort.51").symlink_to(geometry)  # geometry is read from Fortran unit 51
    (work / input_link).symlink_to(input_file)

    options = {
        "external_read_generation_steering.GENERATOR_INPUT_TYPE": generator_type,
        "external_read_generation_steering.INPUT_FILENAMES": input_link,
        "analysis_steering.FILENAME": SGV_OUTPUT,
        **options,
    }
    # steering is read from Fortran unit 17
    (work / "fort.17").write_text(merge_options(steering.read_text(), options))


def run_sgv(
    input_file: Path,
    geometry: Path,
    output: Path,
    options: dict,
    steering: Path | None = None,
    log: Path | None = None,
    keep_workdir: bool = False,
) -> bool:
    """Runs SGV on one file. Output (and log) go to the given paths; returns success.

    The steering defaults to $SGV_DIR/tests/sgv.steer.
    """
    steering = steering or sgv_dir() / "tests/sgv.steer"
    input_file, geometry, steering = (p.resolve() for p in (input_file, geometry, steering))
    output = output.resolve()
    missing = [p for p in (input_file, geometry, steering) if not p.is_file()]
    if missing:
        print(f"SGV not started, missing: {', '.join(map(str, missing))}", file=sys.stderr)
        return False
    output.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="TMP-sgv-", dir=output.parent))
    prepare_workdir(work, input_file, geometry, steering, options)

    with open(log, "w") if log else nullcontext() as stream:
        result = subprocess.run(
            [str(RUN_SGV), str(work)],
            stdout=stream,
            stderr=subprocess.STDOUT,
            env={**os.environ, "SGV_DIR": str(sgv_dir())},
            check=False,  # failures are reported via returncode below
        )

    produced = work / SGV_OUTPUT
    if result.returncode != 0 or not produced.exists():
        print(
            f"SGV failed for {input_file.name} (exit code {result.returncode}), "
            f"work dir kept: {work}",
            file=sys.stderr,
        )
        return False

    shutil.move(produced, output)
    if not keep_workdir:
        shutil.rmtree(work)
    return True


def generator_files(in_dir: Path) -> list[Path]:
    """Generator files directly in in_dir and in sub-directories named like a sample
    (e.g. E250-SetA.P2f_mumu.eL.pR.I403003/), so that folders like validation/ are skipped."""
    dirs = [in_dir]
    for d in sorted(p for p in in_dir.iterdir() if p.is_dir()):
        try:
            parse_sample(d)
            dirs.append(d)
        except ValueError:
            print(f"Skipping directory {d.name}: not a sample")
    return sorted(f for d in dirs for f in d.iterdir() if f.suffix in INPUT_TYPES)


def run_batch(
    in_dir: Path,
    out_dir: Path,
    jobs: int,
    ild_fcc_version: int,
    max_events: int | None,
    steering: Path | None,
) -> bool:
    inputs = generator_files(in_dir)
    if not inputs:
        sys.exit(f"No generator files found in {in_dir}")

    # resolve all settings before starting any job, so configuration errors abort early
    planned = []
    for f in inputs:
        try:
            planned.append((f, collider_settings(parse_sample(f), ild_fcc_version)))
        except ValueError as e:
            print(f"Skipping {f.name}: {e}")

    out_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {}
        for f, settings in planned:
            print(f"{f.name}: {settings.detector_model}, {settings.sgv_geometry.name}")
            options = steering_options(
                max_events,
                settings.cms_energy,
                settings.crossing_angle,
                settings.detector_model,
            )
            futures[f.name] = executor.submit(
                run_sgv,
                f,
                settings.sgv_geometry,
                out_dir / f"{f.stem}.slcio",
                options,
                steering,
                log=out_dir / f"{f.stem}.log",
            )

    failed = [name for name, future in futures.items() if not future.result()]
    if failed:
        print("Failed jobs:\n  " + "\n  ".join(failed), file=sys.stderr)
    else:
        print(f"All {len(futures)} SGV jobs done")
    return not failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run SGV on a single file")
    run.add_argument("input", type=Path, help="Generator file (.slcio/.stdhep)")
    run.add_argument("geometry", type=Path, help="SGV geometry (.inp)")
    run.add_argument("output", type=Path, help="Output .slcio")
    run.add_argument("--cms-energy", type=float)
    run.add_argument("--crossing-angle", type=float, help="Half crossing angle [rad]")
    run.add_argument("--detector", help="Detector name written to the LCIO header")
    run.add_argument("--keep-workdir", action="store_true")

    batch = sub.add_parser("batch", help="Run SGV on all files of a directory")
    batch.add_argument("input_dir", type=Path, nargs="?", help=f"Default: $dtDir/{WHIZARD_SUBDIR}")
    batch.add_argument("output_dir", type=Path, nargs="?", help=f"Default: $dtDir/{SGV_SUBDIR}")
    batch.add_argument("--jobs", type=int, default=8, help="Parallel jobs (default: 8)")
    batch.add_argument("--ild-fcc-version", type=int, choices=(1, 2), default=1)

    for p in (run, batch):
        p.add_argument("--max-events", type=int, help="Default: all events")
        p.add_argument("--steering", type=Path, help="Default: $SGV_DIR/tests/sgv.steer")

    args = parser.parse_args()
    # resolve paths from env vars before any job starts (exits with a message if unset)
    steering = args.steering or sgv_dir() / "tests/sgv.steer"

    if args.command == "run":
        options = steering_options(
            args.max_events, args.cms_energy, args.crossing_angle, args.detector
        )
        ok = run_sgv(
            args.input,
            args.geometry,
            args.output,
            options,
            steering,
            keep_workdir=args.keep_workdir,
        )
    else:
        ok = run_batch(
            args.input_dir or data_dir() / WHIZARD_SUBDIR,
            args.output_dir or data_dir() / SGV_SUBDIR,
            args.jobs,
            args.ild_fcc_version,
            args.max_events,
            steering,
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
