"""Isolated lepton tagging + lepton pairing for the ZH -> ll + X recoil analysis.

Usage:
    MARLIN_DLL=$codeDir/ZHH/source/LeptonPairing/lib/libLeptonPairing.so:$MARLIN_DLL \
    k4run steering_llrecoil.py --inputFiles in.slcio --outputBase out/name \
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

MyIsolatedLeptonTaggingProcessor = MarlinProcessorWrapper("MyIsolatedLeptonTaggingProcessor")
MyIsolatedLeptonTaggingProcessor.OutputLevel = INFO
MyIsolatedLeptonTaggingProcessor.ProcessorType = "IsolatedLeptonTaggingProcessor"
MyIsolatedLeptonTaggingProcessor.Parameters = {
    "CosConeLarge": ["0.95"],
    "CosConeSmall": ["0.98"],
    "CutOnTheISOElectronMVA": ["0.5"],
    "CutOnTheISOMuonMVA": ["0.7"],
    "DirOfISOElectronWeights": [
        "/cvmfs/ilc.desy.de/sw/x86_64_gcc82_centos7/v02-02-02/MarlinReco/v01-31/Analysis/IsolatedLeptonTagging/example/isolated_electron_weights"
    ],
    "DirOfISOMuonWeights": [
        "/cvmfs/ilc.desy.de/sw/x86_64_gcc82_centos7/v02-02-02/MarlinReco/v01-31/Analysis/IsolatedLeptonTagging/example/isolated_muon_weights_woYoke"
    ],
    "InputPandoraPFOsCollection": [PFOCollection],
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
    "OutputIsoLeptonsCollection": ["ISOLeptons"],
    "OutputPFOsWithoutIsoLepCollection": ["PandoraPFOsWithoutIsoLep"],
    "UseYokeForMuonID": ["false"],
}

MyLeptonPairing = MarlinProcessorWrapper("MyLeptonPairing")
MyLeptonPairing.OutputLevel = INFO
MyLeptonPairing.ProcessorType = "LeptonPairing"  # located in ILDAnaSoft/ZHH
MyLeptonPairing.Parameters = {
    "IsoLepCollection": ["ISOLeptons"],
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

MyLCIOOutputProcessor = MarlinProcessorWrapper("MyLCIOOutputProcessor")
MyLCIOOutputProcessor.OutputLevel = INFO
MyLCIOOutputProcessor.ProcessorType = "LCIOOutputProcessor"
MyLCIOOutputProcessor.Parameters = {
    "CompressionLevel": ["6"],
    "LCIOOutputFile": [f"{OutputBaseName}.slcio"],
    "LCIOWriteMode": ["WRITE_NEW"],
}

algList.append(MyIsolatedLeptonTaggingProcessor)
algList.append(MyLeptonPairing)
algList.append(MyLCIOOutputProcessor)

from Configurables import ApplicationMgr

ApplicationMgr(
    TopAlg=algList, EvtSel="NONE", EvtMax=args.nEvents, ExtSvc=svcList, OutputLevel=INFO
)
