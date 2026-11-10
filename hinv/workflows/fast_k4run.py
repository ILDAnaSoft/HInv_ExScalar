"""hep_workflows configurations of the ZH -> ll + invisible analysis with SGV fast simulation and
k4run based high-level reconstruction (steering/llrecoil.py), one per collider:

    250-ilc-hinv-fast-k4run    ILD@ILC, all E250-SetA samples
    240-fcc-hinv-fast-k4run    ILD@FCC, all E240-FCCee_PB samples

The input are the existing WHIZARD files in $dtDir/<WHIZARD_SUBDIR> (see paths.py), i.e. no
event generation is run. The SGV settings (energy, crossing angle, geometry, detector name) are
chosen per file as in hinv.sim.sgv, see samples.py. The configurations run up to and including
RecoFinal; the analysis tasks are not used.

Usage (hep_workflows environment set up, this repository installed, see the README). All jobs
need $dtDir, the reco jobs also $codeDir, see lepton_pairing_lib:
    law run RecoFinal --tag=250-ilc-hinv-fast-k4run

NOTE: 240-fcc-hinv-fast-k4run needs a key4hep release containing ILD_FCCee_v01 in $K4GEO for the
reco tasks, e.g. K4H_RELEASE=2026-04-08 (2025-01-28 does not have it).

In the future, the event generation itself can be added, too. Define the whizard_options under
an AnalysisConfiguration for this to work. See hep_workflows/configs/test_e250_zh_fast_k4run.py
as an example.
"""

from hep_workflows.framework import (
    EVENT_SIM_ENUM,
    RECO_ANA_RUNMODES,
    AnalysisConfiguration,
    configurations,
)

from hinv.paths import WHIZARD_SUBDIR, data_dir
from hinv.samples import FCCEE, ILC, REPO_DIR, collider_settings, parse_sample
from hinv.sim.sgv import SGV_OUTPUT


class HInvFastK4RunConfig(AnalysisConfiguration):
    collider: str
    ild_fcc_version = 1

    # LeptonPairingCombined, used by llrecoil.py; expanded in the job (see paths.lepton_pairing_lib)
    lepton_pairing_lib = "$codeDir/ZHH/source/LeptonPairing/lib/libLeptonPairing.so"

    simulation = EVENT_SIM_ENUM.FAST_SGV
    high_level_reco = RECO_ANA_RUNMODES.K4RUN
    analysis = RECO_ANA_RUNMODES.K4RUN

    def __init__(self):
        self.task_kwargs = {
            # FastSimSGV runs with one geometry for all branches; set it per input file
            "FastSimSGV": lambda task: {"geometry_file": str(self.settings(task.branch_data[0]).sgv_geometry)},
            "RecoAbstract": {
                "steering_file": str(REPO_DIR / "steering/llrecoil.py"),
                "output_file": "reco.slcio",
                "build_run_command": self.llrecoil_command,
                # llrecoil.py has no --MCParticleCollectionName argument
                "pass_mcp_col_name": False,
                # cap the number of events if not given by the chunk plan, i.e. for RecoRuntime
                "n_events_max": 50,
            },
        }
        super().__init__()

    @property
    def detector_model(self) -> str:
        return f"ILD_FCCee_v{self.ild_fcc_version:02d}" if self.collider == FCCEE else "ILD_l5_o1_v02"

    def llrecoil_command(self, task, steering) -> str:
        """Replaces AbstractRecoAna.build_run_command, which passes --compactFile and --outputFile:
        steering/llrecoil.py takes --detectorModel and --outputBase instead. Also adds
        LeptonPairing to MARLIN_DLL."""
        files_arg = " ".join(f'"{f}"' for f in steering["input_files"])
        output_base = steering["output_file"].removesuffix(".slcio")
        n_events_max, n_events_skip = steering["n_events_max"], steering["n_events_skip"]

        cmd = f'[ -f "{self.lepton_pairing_lib}" ] || {{ echo "Not found: {self.lepton_pairing_lib}"; false; }}'
        cmd += f' && MARLIN_DLL="{self.lepton_pairing_lib}:$MARLIN_DLL" {steering["executable"]} "{task.steering_file}"'
        cmd += f" --inputFiles {files_arg}"
        cmd += f' --outputBase "{output_base}" --detectorModel {self.detector_model}'
        cmd += f" --nEvents {n_events_max if n_events_max is not None and n_events_max > 0 else -1}"
        if n_events_skip is not None and n_events_skip > 0:
            cmd += f" --LcioEvent.skipNEvents={n_events_skip}"
        return f"( {cmd} {task.parse_constants()} {task.parse_globals()} )"

    def settings(self, path: str):
        return collider_settings(parse_sample(path), self.ild_fcc_version)

    def input_files(self) -> list[str]:
        # one sub-directory per sample, e.g. E250-SetA.P2f_mumu.eL.pR.I403003/
        files = sorted(str(f) for f in (data_dir() / WHIZARD_SUBDIR).glob("E*/*.slcio"))
        return [f for f in files if parse_sample(f).collider == self.collider]

    def sgv_inputs(self, task):
        files = self.input_files()
        options = []
        for f in files:
            settings = self.settings(f)
            options.append({
                "global_steering.MAXEV": 999999,
                "global_generation_steering.CMS_ENE": settings.cms_energy,
                "global_generation_steering.CROSSING_ANGLE": settings.crossing_angle,
                "external_read_generation_steering.GENERATOR_INPUT_TYPE": "LCIO",
                "external_read_generation_steering.INPUT_FILENAMES": "input.slcio",
                "analysis_steering.FILENAME": SGV_OUTPUT,
                "analysis_steering.DETECTOR": settings.detector_model,
            })
        return files, options


class E250ILCHInvConfig(HInvFastK4RunConfig):
    tag = "250-ilc-hinv-fast-k4run"
    sqrt_s = 250.0
    collider = ILC


class E240FCCHInvConfig(HInvFastK4RunConfig):
    tag = "240-fcc-hinv-fast-k4run"
    sqrt_s = 240.0
    collider = FCCEE


configurations.add(E250ILCHInvConfig())
configurations.add(E240FCCHInvConfig())
