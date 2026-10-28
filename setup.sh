# Source this file to make the hinv package importable:
#     source setup.sh
# Scripts are then run as modules from anywhere, e.g. python -m hinv.sim.sgv batch

HINV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HINV_DIR

case ":${PYTHONPATH}:" in
    *":${HINV_DIR}:"*) ;;
    *) export PYTHONPATH="${HINV_DIR}${PYTHONPATH:+:${PYTHONPATH}}" ;;
esac
