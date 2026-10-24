#!/usr/bin/env bash
# Run steering_llrecoil.py on all SGV files of a directory in parallel.
# The detector model is chosen per collider, see detector_models.sh.
# Usage: [ILD_FCC_VERSION=1|2] run_reco_all.sh <sgv_dir> <output_dir>
IN_DIR=$1; OUT_DIR=$2
SCRIPT_DIR=$(dirname "$(realpath "$0")")
codeDir=${codeDir:-/data/dust/user/schwanvl/promotion/code}
source "$SCRIPT_DIR/detector_models.sh"

[[ -z "${KEY4HEP_STACK:-}" ]] && source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08 > /dev/null
export MARLIN_DLL=$codeDir/ZHH/source/LeptonPairing/lib/libLeptonPairing.so:$MARLIN_DLL
mkdir -p "$OUT_DIR"

for f in "$IN_DIR"/*.slcio; do
    b=$(basename "$f" .slcio)
    collider_settings "$b" || { echo "Skipping $b: unknown collider"; continue; }
    echo "$b: $DETECTOR"
    # separate work dirs: Marlin writes cdb.log etc. into the CWD
    mkdir -p "$OUT_DIR/work/$b"
    ( cd "$OUT_DIR/work/$b" && k4run "$SCRIPT_DIR/steering_llrecoil.py" \
        --inputFiles "$f" --outputBase "$OUT_DIR/$b" --detectorModel "$DETECTOR" \
        > "$OUT_DIR/$b.log" 2>&1 || echo "FAILED: $b" ) &
done
wait
rm -rf "$OUT_DIR/work"
echo "All reco jobs finished"
