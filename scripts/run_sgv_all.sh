#!/usr/bin/env bash
# Run SGV on all WHIZARD files of a directory in parallel.
# Geometry/energy/crossing angle are chosen per collider, see detector_models.sh.
# Usage: [ILD_FCC_VERSION=1|2] run_sgv_all.sh <input_dir> <output_dir>
IN_DIR=$1; OUT_DIR=$2
SCRIPT_DIR=$(dirname "$(realpath "$0")")
source "$SCRIPT_DIR/detector_models.sh"
mkdir -p "$OUT_DIR"

for f in "$IN_DIR"/*.slcio; do
    b=$(basename "$f")
    collider_settings "$b" || { echo "Skipping $b: unknown collider"; continue; }
    echo "$b: $DETECTOR, $(basename "$SGV_GEO")"
    CMS_ENE=$CMS_ENE CROSSING_ANGLE=$CROSSING_ANGLE DETECTOR=$DETECTOR \
        "$SCRIPT_DIR/run_sgv" "$f" "$SGV_GEO" "$OUT_DIR/$b" \
        > "$OUT_DIR/${b%.slcio}.log" 2>&1 &
done
wait
failed=$(grep -L "^Done:" "$OUT_DIR"/*.log)
[[ -n "$failed" ]] && echo -e "Failed jobs:\n$failed" || echo "All SGV jobs done"
