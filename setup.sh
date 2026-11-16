# Source this file to set up the environment of the analysis:
#     source setup.sh
# This sets up key4hep (if not done yet), activates the .venv of this repository and makes ZHH
# importable. Scripts are then run as modules from anywhere, e.g. python -m hinv.sim.sgv batch

HINV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export HINV_DIR

# first key4hep: the venv is built on top of its Python
if [ -z "${KEY4HEP_STACK:-}" ]; then
    source /cvmfs/sw.hsf.org/key4hep/setup.sh -r 2026-04-08 > /dev/null
fi

if [ -f "$HINV_DIR/.venv/bin/activate" ]; then
    source "$HINV_DIR/.venv/bin/activate"
else
    echo "Note: $HINV_DIR/.venv does not exist, see 'Setup' in the README."
fi

_hinv_prepend_pythonpath() {
    case ":${PYTHONPATH}:" in
        *":$1:"*) ;;
        *) export PYTHONPATH="$1${PYTHONPATH:+:${PYTHONPATH}}" ;;
    esac
}

_hinv_prepend_pythonpath "$HINV_DIR"

# ZHH as a library for the cutflow tool. It is not pip-installed: this would register its
# hep_workflows plugin, and importing hep_workflows would then need the whole ZHH environment.
if [ -d "${codeDir:-}/ZHH/zhh" ]; then
    _hinv_prepend_pythonpath "$codeDir/ZHH"
else
    echo "Note: \$codeDir/ZHH not found, the cutflow tool will not be available."
fi

unset -f _hinv_prepend_pythonpath
