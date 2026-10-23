from Gaudi.Configuration import *

from Configurables import LcioEvent, EventDataSvc, MarlinProcessorWrapper, GeoSvc

from os import environ

algList = []
svcList = []
evtsvc = EventDataSvc()

svcList.append(evtsvc)

DetectorModel = "ILD_l5_o1_v02"
CompactFile = f"{environ['k4geo_DIR']}/ILD/compact/{DetectorModel}/{DetectorModel}.xml"
OutputDirectory = "."
OutputBaseName = "ZZ_sl_LR"
PFOCollection = "PandoraPFOs"

read = LcioEvent()
read.OutputLevel = DEBUG
read.Files = [
    "/pnfs/desy.de/ilc/prod/ilc/mc-2020/ild/dst-merged/250-SetA/4f_ZZ_semileptonic/ILD_l5_o2_v02/v02-02-01/00015655/000/rv02-02-01.sv02-02.mILD_l5_o2_v02.E250-SetA.I500074.P4f_zz_sl.eL.pR.n000.d_dstm_15655_0.slcio"
]
algList.append(read)

geoSvc = GeoSvc("GeoSvc")
geoSvc.OutputLevel = DEBUG
geoSvc.EnableGeant4Geo = False
geoSvc.detectors = [CompactFile]
svcList.append(geoSvc)


MyIsolatedLeptonTaggingProcessor = MarlinProcessorWrapper("MyIsolatedLeptonTaggingProcessor")
MyIsolatedLeptonTaggingProcessor.OutputLevel = DEBUG
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
MyLeptonPairing.OutputLevel = DEBUG
MyLeptonPairing.ProcessorType = "LeptonPairing" # located in ILDAnaSoft/ZHH
MyLeptonPairing.Parameters = {
    "ISOLeptons": ["ISOLeptons"],
    "LeptonPair": ["LeptonPair"],
    "PandoraPFOsWithoutIsoLep": ["PandoraPFOsWithoutIsoLep"],
    "PandoraPFOsWithoutLepPair": ["PandoraPFOsWithoutLepPair"],
    "RootFile": [f"{OutputDirectory}/{OutputBaseName}_LeptonPairing.root"],
    "fillRootTree": ["true"],
}

IsolatedPhotonTagging = MarlinProcessorWrapper("IsolatedPhotonTagging")
IsolatedPhotonTagging.ProcessorType = "IsolatedPhotonTaggingProcessor"
IsolatedPhotonTagging.Parameters = {
    "CosConeLarge": ["0.95"],
    "CosConeSmall": ["0.98"],
    "CutOnTheISOPhotonMVA": ["0.5"],
    "DirOfIsoPhotonWeights": ["isolated_photon_weights"],
    "InputPandoraPFOsCollection": ["PandoraPFOsWithoutIsoLep"],
    "IsSelectingOneIsoPhoton": ["false"],
    "MinEForPhoton": ["5."],
    "OutputIsoPhotonsCollection": ["IsolatedPhotons"],
}

MyFastJetProcessor = MarlinProcessorWrapper("MyFastJetProcessor")
MyFastJetProcessor.OutputLevel = DEBUG
MyFastJetProcessor.ProcessorType = "FastJetProcessor"
MyFastJetProcessor.Parameters = {
    "algorithm": ["kt_algorithm", "1.3"],
    "clusteringMode": ["ExclusiveNJets", "4"],
    "jetOut": ["FastJets4_Precluster"],
    "recParticleIn": ["PandoraPFOs"],
    "recParticleOut": ["RefinedJets"],
    "recombinationScheme": ["E_scheme"],
    "storeParticlesInJets": ["true"],
}

MyLCIOOutputProcessor = MarlinProcessorWrapper("MyLCIOOutputProcessor")
MyLCIOOutputProcessor.OutputLevel = DEBUG
MyLCIOOutputProcessor.ProcessorType = "LCIOOutputProcessor"
MyLCIOOutputProcessor.Parameters = {
    "CompressionLevel": ["6"],
    "LCIOOutputFile": [f"{OutputDirectory}/{OutputBaseName}.slcio"],
    "LCIOWriteMode": ["WRITE_NEW"],
}

algList.append(MyIsolatedLeptonTaggingProcessor)
# algList.append(MyLeptonPairing) # located in ILDAnaSoft/ZHH
algList.append(IsolatedPhotonTagging)
algList.append(MyFastJetProcessor)
algList.append(MyLCIOOutputProcessor)

from Configurables import ApplicationMgr

ApplicationMgr(TopAlg=algList, EvtSel="NONE", EvtMax=10, ExtSvc=svcList, OutputLevel=DEBUG)
