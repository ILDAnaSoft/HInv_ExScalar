"""Isolated lepton and photon tagging + lepton pairing for the ZH -> ll + X recoil analysis.

Isolated muons and electrons are tagged in two passes (muons first, electrons on the remaining
PFOs) and paired by LeptonPairingCombined, as in ZHH's scripts/prod_reco.xml.

Isolated photons are tagged independently on the full PandoraPFOs collection, so that the
leptons are in the isolation cones: on PFOs without leptons, FSR photons would look isolated.
The processor only creates subset collections and leaves the lepton tagging unchanged.

Usage:
    MARLIN_DLL=$codeDir/ZHH/source/LeptonPairing/lib/libLeptonPairing.so:$MARLIN_DLL \
    k4run llrecoil.py --inputFiles in.slcio --outputBase out/name \
        [--nEvents N] [--detectorModel ILD_FCCee_v01]
"""

from Gaudi.Configuration import *

from Configurables import LcioEvent, EventDataSvc, MarlinProcessorWrapper, GeoSvc
from k4FWCore.parseArgs import parser

from os import environ

parser.add_argument("--inputFiles", nargs="+", required=True, help="Input (SGV) LCIO files")
parser.add_argument("--outputBase", required=True, help="Output path without extension")
parser.add_argument("--nEvents", type=int, default=-1, help="Number of events (-1: all)")
parser.add_argument(
    "--detectorModel",
    default="ILD_l5_o1_v02",
    help="Full-sim detector model, e.g. ILD_l5_o1_v02 (ILD@ILC) or ILD_FCCee_v01 (ILD@FCC)",
)
args = parser.parse_known_args()[0]

# models living in $K4GEO/FCCee/ILD_FCCee/ (cf. ILDConfig/StandardConfig/production/ILDReconstruction.py)
FCCEE_MDI_DETECTOR_MODELS_COMMON_MDI = ("ILD_FCCee_v01", "ILD_FCCee_v02")


def get_compact_file_path(detector_model: str) -> str:
    if detector_model in FCCEE_MDI_DETECTOR_MODELS_COMMON_MDI:
        return f"{environ['K4GEO']}/FCCee/ILD_FCCee/compact/{detector_model}/{detector_model}.xml"
    return f"{environ['K4GEO']}/ILD/compact/{detector_model}/{detector_model}.xml"


algList = []
svcList = []
evtsvc = EventDataSvc()

svcList.append(evtsvc)

DetectorModel = args.detectorModel
CompactFile = get_compact_file_path(DetectorModel)
OutputBaseName = args.outputBase
PFOCollection = "PandoraPFOs"

read = LcioEvent()
read.OutputLevel = INFO
read.Files = args.inputFiles
algList.append(read)

geoSvc = GeoSvc("GeoSvc")
geoSvc.OutputLevel = INFO
geoSvc.EnableGeant4Geo = False
geoSvc.detectors = [CompactFile]
svcList.append(geoSvc)

ISOLEP_WEIGHTS_DIR = "/cvmfs/ilc.desy.de/sw/x86_64_gcc82_centos7/v02-02-02/MarlinReco/v01-31/Analysis/IsolatedLeptonTagging/example"
MVA_CUT_DISABLED = "2"  # the MVA output is at most 1, so this cut rejects all candidates


def isolated_lepton_tagging(name, input_pfos, output_isoleps, output_pfos, muon_cut, electron_cut):
    proc = MarlinProcessorWrapper(name)
    proc.OutputLevel = INFO
    proc.ProcessorType = "IsolatedLeptonTaggingProcessor"
    proc.Parameters = {
        "CosConeLarge": ["0.95"],
        "CosConeSmall": ["0.98"],
        "CutOnTheISOElectronMVA": [electron_cut],
        "CutOnTheISOMuonMVA": [muon_cut],
        "DirOfISOElectronWeights": [f"{ISOLEP_WEIGHTS_DIR}/isolated_electron_weights"],
        "DirOfISOMuonWeights": [f"{ISOLEP_WEIGHTS_DIR}/isolated_muon_weights_woYoke"],
        "InputPandoraPFOsCollection": [input_pfos],
        "InputPrimaryVertexCollection": ["PrimaryVertex"],
        "IsSelectingOneIsoLep": ["false"],
        "MaxD0SigForElectron": ["50"],
        "MaxD0SigForMuon": ["20"],
        "MaxEOverPForElectron": ["1.3"],
        "MaxEOverPForMuon": ["0.3"],
        "MaxZ0SigForElectron": ["50"],
        "MaxZ0SigForMuon": ["20"],
        "MinEOverPForElectron": ["0.5"],
        "MinEecalOverTotEForElectron": ["0.9"],
        "MinEyokeForMuon": ["1.2"],
        "MinPForElectron": ["5"],
        "MinPForMuon": ["5"],
        "OutputIsoLeptonsCollection": [output_isoleps],
        "OutputPFOsWithoutIsoLepCollection": [output_pfos],
        "UseYokeForMuonID": ["false"],
    }
    return proc


MyIsolatedMuonTagging = isolated_lepton_tagging(
    "MyIsolatedMuonTagging",
    input_pfos=PFOCollection,
    output_isoleps="ISOMuons",
    output_pfos="PandoraPFOsWithoutIsoMuons",
    muon_cut="0.7",
    electron_cut=MVA_CUT_DISABLED,
)
MyIsolatedElectronTagging = isolated_lepton_tagging(
    "MyIsolatedElectronTagging",
    input_pfos="PandoraPFOsWithoutIsoMuons",
    output_isoleps="ISOElectrons",
    output_pfos="PandoraPFOsWithoutIsoLep",
    muon_cut=MVA_CUT_DISABLED,
    electron_cut="0.5",
)

MyLeptonPairing = MarlinProcessorWrapper("MyLeptonPairing")
# WARNING: LeptonPairingCombined prints a MESSAGE for every event without tau collection
MyLeptonPairing.OutputLevel = WARNING
MyLeptonPairing.ProcessorType = "LeptonPairingCombined"  # located in ILDAnaSoft/ZHH
MyLeptonPairing.Parameters = {
    "IsoElectronCollection": ["ISOElectrons"],
    "IsoMuonCollection": ["ISOMuons"],
    "IsoTauCollection": ["ISOTaus"],  # optional, ignored if not present
    "PFOsWOIsoLepCollection": ["PandoraPFOsWithoutIsoLep"],
    "LepPairCollection": ["LeptonPair"],
    "PFOsWOLepPairCollection": ["PandoraPFOsWithoutLepPair"],
    "IsoLepPairCollection": ["IsoLeptonPair"],
    "diLepInvMass": [
        "91.1879"
    ],  # from (Particle Data Group), Int. J. Mod. Phys. A 41, 2630011 (2026) @ https://pdg.lbl.gov/2026/listings/rpp2026-list-z-boson.pdf
    "doPhotonRecovery": ["true"],
    "RootFile": [f"{OutputBaseName}_LeptonPairing.root"],
    "fillRootTree": ["true"],
}

# Cut-based (the MVA parameters of the processor are unused): a neutral PFO of type 22 with
# E > MinEForPhoton is isolated if the charged (neutral) energy in the cone CosConeSmall is below
# RatioChargedConeEnergy (RatioNeutralConeEnergy) times its energy.
MyIsolatedPhotonTagging = MarlinProcessorWrapper("MyIsolatedPhotonTagging")
MyIsolatedPhotonTagging.OutputLevel = INFO
MyIsolatedPhotonTagging.ProcessorType = "IsolatedPhotonTaggingProcessor"
MyIsolatedPhotonTagging.Parameters = {
    "InputPandoraPFOsCollection": [PFOCollection],
    "OutputIsoPhotonsCollection": ["ISOPhotons"],
    "OutputPFOsWithoutIsoPhotonCollection": ["PandoraPFOsWithoutIsoPhoton"],
    "IsSelectingOneIsoPhoton": ["false"],  # keep all isolated photons, not only the hardest
    "MinEForPhoton": ["5"],  # [GeV]
    "CosConeSmall": ["0.98"],
    # no effect: the processor sums the PFOs in this cone into a four-momentum it never uses
    # (MarlinReco 1.38, Utilities.cc getConeEnergy)
    "CosConeLarge": ["0.95"],
    "RatioChargedConeEnergy": ["0.1"],
    "RatioNeutralConeEnergy": ["0.2"],
}

MyLCIOOutputProcessor = MarlinProcessorWrapper("MyLCIOOutputProcessor")
MyLCIOOutputProcessor.OutputLevel = INFO
MyLCIOOutputProcessor.ProcessorType = "LCIOOutputProcessor"
MyLCIOOutputProcessor.Parameters = {
    "CompressionLevel": ["6"],
    "LCIOOutputFile": [f"{OutputBaseName}.slcio"],
    "LCIOWriteMode": ["WRITE_NEW"],
}

algList.append(MyIsolatedMuonTagging)
algList.append(MyIsolatedElectronTagging)
algList.append(MyLeptonPairing)
algList.append(MyIsolatedPhotonTagging)
algList.append(MyLCIOOutputProcessor)

from Configurables import ApplicationMgr

ApplicationMgr(
    TopAlg=algList, EvtSel="NONE", EvtMax=args.nEvents, ExtSvc=svcList, OutputLevel=INFO
)
