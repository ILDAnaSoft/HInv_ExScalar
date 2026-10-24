# Collider-dependent settings, shared by run_sgv_all.sh and run_reco_all.sh.
# Source this file and call `collider_settings <sample file name>`; it sets
#   CMS_ENE, CROSSING_ANGLE (half angle) : SGV steering overrides
#   SGV_GEO                              : SGV detector geometry
#   DETECTOR                             : full-sim model (Gaudi steering + LCIO header)
#
# ILD@FCC version: ILD_FCC_VERSION=1 (default) or 2

_REPO_DIR=$(dirname "$(dirname "$(realpath "${BASH_SOURCE[0]}")")")
SGV_DIR=${SGV_DIR:-/data/dust/user/schwanvl/promotion/code/SGV_install/sgv}
ILD_FCC_VERSION=${ILD_FCC_VERSION:-1}

collider_settings() {
    case "$(basename "$1")" in
        E240-FCCee*)  # FCC-ee: 30 mrad full crossing angle
            CMS_ENE=240.0; CROSSING_ANGLE=0.015
            SGV_GEO=$_REPO_DIR/sgv_geometries/sgv_geo_fullsim_ildfcc_v${ILD_FCC_VERSION}.inp
            DETECTOR=ILD_FCCee_v0${ILD_FCC_VERSION} ;;
        E250*)        # ILC: 14 mrad full crossing angle
            CMS_ENE=250.0; CROSSING_ANGLE=0.007
            SGV_GEO=$SGV_DIR/tests/sgv_geo.inp
            DETECTOR=ILD_l5_o1_v02 ;;
        *) return 1 ;;
    esac
    [[ -f "$SGV_GEO" ]] || { echo "SGV geometry not found: $SGV_GEO" >&2; return 1; }
}
