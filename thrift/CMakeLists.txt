# ============================================================================
# TAAC Thrift -> Python Codegen
# ============================================================================
# Two sources of .thrift files:
#   1. TAAC-owned: ${TAAC_THRIFT_DIR} (thrift/ directory in THIS repo)
#   2. FBOSS:     ${FBOSS_THRIFT_DIR} (fetched by getdeps fboss-thrift-defs)
# ============================================================================

set(TAAC_THRIFT_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(FBOSS_THRIFT_DIR "${FBOSS_THRIFT_SOURCE_DIR}")

# add_taac_thrift_python_library() propagates thrift1 -I paths via its DEPENDS
# list. Each DEPENDS entry <X> contributes X.thrift_includes to the target.
# Declare an INTERFACE library exposing both thrift source roots, and have
# every add_taac_thrift_python_library() call below DEPENDS on it so "include ..."
# statements resolve across both trees.
#
# (Don't use add_fbthrift_python_library's THRIFT_INCLUDE_DIR kwarg for
# this; it takes a single install-time path, not a list of thrift1 search
# dirs.)
# fbthrift ships annotation files (e.g. thrift/annotation/thrift.thrift)
# at <install_prefix>/include/. FBThrift_DIR points at
# <install_prefix>/lib/cmake/fbthrift/, so go up three levels + into include/.
get_filename_component(FBTHRIFT_ANNOTATION_INCLUDE
    "${FBThrift_DIR}/../../../include" ABSOLUTE
)

add_library(thrift_roots.thrift_includes INTERFACE)
target_include_directories(thrift_roots.thrift_includes
    INTERFACE
    "${TAAC_THRIFT_DIR}"
    "${FBOSS_THRIFT_DIR}"
    "${FBTHRIFT_ANNOTATION_INCLUDE}"
)
# add_taac_thrift_python_library() also passes DEPENDS to add_fb_python_library,
# which requires <name>.py_lib to exist (linked against) and triggers an
# add_dependencies() call. Declare empty stand-ins so "DEPENDS thrift_roots"
# satisfies both the thrift-compiler include propagation AND the Python
# library dependency accounting, without pretending thrift_roots has
# any Python sources.
add_library(thrift_roots.py_lib INTERFACE)
add_custom_target(thrift_roots.py_sources_built)

# Wrapper around add_fbthrift_python_library: that macro hard-codes
# "${CMAKE_CURRENT_SOURCE_DIR}/${THRIFT_FILE}", so an absolute THRIFT_FILE
# produces a doubled path like "/taac/thrift//scratch/.../ctrl.thrift".
# Convert the path to CMAKE_CURRENT_SOURCE_DIR-relative before forwarding.
function(add_taac_thrift_python_library LIB_NAME THRIFT_PATH)
    cmake_path(RELATIVE_PATH THRIFT_PATH
        BASE_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        OUTPUT_VARIABLE REL_PATH
    )
    add_fbthrift_python_library("${LIB_NAME}" "${REL_PATH}" ${ARGN})
    # Each library's generated Python tree lives at
    # ${CMAKE_CURRENT_BINARY_DIR}/${REL_PATH}-python/gen-python/. Merge
    # every library's gen-python into the same site-packages destination
    # so all namespaces coexist as a single importable tree.
    install(
        DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/${REL_PATH}-python/gen-python/"
        DESTINATION "lib/python3/site-packages"
        FILES_MATCHING PATTERN "*.py"
    )
endfunction()

# ============================================================================
# SECTION A: Common / Shared (from FBOSS)
# ============================================================================

# facebook.network.Address
add_taac_thrift_python_library(
    network_address_py
    "${FBOSS_THRIFT_DIR}/common/network/if/Address.thrift"
    NAMESPACE "facebook.network"
    OPTIONS json
    DEPENDS thrift_roots
)

# fb303 — imported transitively by FBOSS-generated code (ctrl.thrift etc.
# emit `import fb303.thrift_abstract_types`). The .thrift file has no
# `namespace py3`, so mstch_python places output at gen-python/fb303/.
add_taac_thrift_python_library(
    fb303_py
    "${FBOSS_THRIFT_DIR}/common/fb303/if/fb303.thrift"
    OPTIONS json
    DEPENDS thrift_roots
)

# ============================================================================
# SECTION B: FBOSS Thrift (from fetched source)
# ============================================================================

add_taac_thrift_python_library(
    mpls_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/mpls.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    fboss_common_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/if/fboss_common.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    fboss_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/fboss.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    common_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/common.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots mpls_py network_address_py
)

add_taac_thrift_python_library(
    switch_config_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/switch_config.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots common_py fboss_common_py mpls_py
)

add_taac_thrift_python_library(
    ctrl_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/ctrl.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots common_py fboss_py mpls_py switch_config_py network_address_py
)

add_taac_thrift_python_library(
    hw_ctrl_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/hw_ctrl.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots ctrl_py common_py fboss_py
)

add_taac_thrift_python_library(
    hardware_stats_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/hw/hardware_stats.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    prbs_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/prbs.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    link_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/link.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    transceiver_py
    "${FBOSS_THRIFT_DIR}/fboss/qsfp_service/if/transceiver.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots prbs_py link_py
)

add_taac_thrift_python_library(
    phy_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/phy.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots prbs_py link_py transceiver_py switch_config_py
)

add_taac_thrift_python_library(
    fsdb_py
    "${FBOSS_THRIFT_DIR}/fboss/fsdb/if/fsdb.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

# Transitive deps of ctrl.thrift / phy.thrift generated Python. Not
# imported directly by TAAC, but their thrift_abstract_types modules
# are referenced from the corresponding thrift_abstract_types of ctrl /
# phy / etc., so they must exist as importable packages at runtime.
add_taac_thrift_python_library(
    io_stats_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/if/io_stats.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    product_info_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/product_info.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    asic_temp_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/asic_temp.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    agent_stats_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/agent_stats.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    bcm_config_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/hw/bcm/bcm_config.thrift"
    NAMESPACE "neteng.fboss.bcm_config"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    asic_config_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/hw/sai/config/asic_config.thrift"
    NAMESPACE "neteng.fboss.asic_config"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    asic_config_v2_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/hw/config/asic_config_v2.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    platform_config_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/platform_config.thrift"
    NAMESPACE "neteng.fboss.platform_config"
    OPTIONS json
    DEPENDS thrift_roots
)
# Distinct from fboss_common_py above (fboss/lib/if/fboss_common.thrift);
# this is the configerator-side common thrift included by ctrl.thrift
# with the alias 'as fboss_common'.
add_taac_thrift_python_library(
    fboss_configerator_common_py
    "${FBOSS_THRIFT_DIR}/configerator/structs/neteng/fboss/thrift/common.thrift"
    NAMESPACE "neteng.fboss.configerator"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    mka_structs_py
    "${FBOSS_THRIFT_DIR}/fboss/mka_service/if/mka_structs.thrift"
    NAMESPACE "neteng.fboss.mka"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    patch_py
    "${FBOSS_THRIFT_DIR}/fboss/thrift_cow/patch.thrift"
    NAMESPACE "neteng.fboss.thrift_cow"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    fsdb_common_py
    "${FBOSS_THRIFT_DIR}/fboss/fsdb/if/fsdb_common.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    fsdb_oper_py
    "${FBOSS_THRIFT_DIR}/fboss/fsdb/if/fsdb_oper.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    highfreq_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/highfreq.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)
add_taac_thrift_python_library(
    switch_state_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/switch_state.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    DEPENDS thrift_roots
)

# ============================================================================
# SECTION C: TAAC-Owned Thrift (from this repo)
# ============================================================================

add_taac_thrift_python_library(
    qosdb_cos_py
    "${TAAC_THRIFT_DIR}/configerator/structs/neteng/qosdb/Cos.thrift"
    NAMESPACE "neteng.qosdb"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    ixia_py
    "${TAAC_THRIFT_DIR}/configerator/structs/neteng/ixia/ixia.thrift"
    NAMESPACE "ixia"
    OPTIONS json
    DEPENDS thrift_roots
)

# Leaf QoS enum used by the ixia_config_thrift schema below.
add_taac_thrift_python_library(
    qos_config_py
    "${TAAC_THRIFT_DIR}/neteng/test_infra/dne/utils/if/qos_config.thrift"
    NAMESPACE "neteng.test_infra.dne.utils"
    OPTIONS json
    DEPENDS thrift_roots
)

# IXIA traffic config schema. taac/driver/driver_constants.py imports
# `from neteng.test_infra.ixia.ixnetwork_restpy.ixia_config_thrift import types`
# and populates module-level data structures from the generated enums, so
# this binding must exist at runtime.
add_taac_thrift_python_library(
    ixia_config_thrift_py
    "${TAAC_THRIFT_DIR}/ixia/ixia_config_thrift.thrift"
    NAMESPACE "neteng.test_infra.ixia.ixnetwork_restpy"
    OPTIONS json
    DEPENDS thrift_roots
)

add_taac_thrift_python_library(
    health_check_py
    "${TAAC_THRIFT_DIR}/configerator/structs/neteng/taac/health_check.thrift"
    NAMESPACE "taac.health_check"
    OPTIONS json
    DEPENDS thrift_roots qosdb_cos_py
)

add_taac_thrift_python_library(
    test_as_a_config_py
    "${TAAC_THRIFT_DIR}/configerator/structs/neteng/taac/test_as_a_config.thrift"
    NAMESPACE "taac"
    OPTIONS json
    DEPENDS thrift_roots health_check_py ixia_py
)

# ============================================================================
# SECTION D: Install generated Python to site-packages
# ============================================================================

# add_fbthrift_py_library's .py_sources_built targets are not part of
# `ninja all` by default, so `cmake --install` (which first triggers
# the default-built targets) would not generate any thrift Python
# before copying gen-py/. Force-build every thrift target by making an
# ALL-declared aggregate depend on their .py_sources_built targets.
# Keep this list in sync with the add_taac_thrift_python_library calls above.
add_custom_target(all_thrift_bindings ALL DEPENDS
    network_address_py.py_sources_built
    fb303_py.py_sources_built
    mpls_py.py_sources_built
    fboss_common_py.py_sources_built
    fboss_py.py_sources_built
    common_py.py_sources_built
    switch_config_py.py_sources_built
    ctrl_py.py_sources_built
    hw_ctrl_py.py_sources_built
    hardware_stats_py.py_sources_built
    prbs_py.py_sources_built
    link_py.py_sources_built
    transceiver_py.py_sources_built
    phy_py.py_sources_built
    fsdb_py.py_sources_built
    io_stats_py.py_sources_built
    product_info_py.py_sources_built
    asic_temp_py.py_sources_built
    agent_stats_py.py_sources_built
    bcm_config_py.py_sources_built
    asic_config_py.py_sources_built
    asic_config_v2_py.py_sources_built
    platform_config_py.py_sources_built
    fboss_configerator_common_py.py_sources_built
    mka_structs_py.py_sources_built
    patch_py.py_sources_built
    fsdb_common_py.py_sources_built
    fsdb_oper_py.py_sources_built
    highfreq_py.py_sources_built
    switch_state_py.py_sources_built
    qosdb_cos_py.py_sources_built
    ixia_py.py_sources_built
    qos_config_py.py_sources_built
    ixia_config_thrift_py.py_sources_built
    health_check_py.py_sources_built
    test_as_a_config_py.py_sources_built
)

# Per-library install rules are emitted inside the add_taac_thrift_python_library
# wrapper above (${CMAKE_CURRENT_BINARY_DIR}/<name>-python/gen-python/ into
# lib/python3/site-packages), so no aggregate install(DIRECTORY ...) is
# needed here.

# Compatibility shims. mstch_python produces thrift_types.py and
# thrift_clients.py, but the TAAC Python code imports the legacy-style
# aliases `types` / `ttypes` / `clients` (e.g. `from ixia.ixia import
# types`). After the gen-python tree is installed, emit a one-line shim
# next to every generated module so both naming conventions work.
install(CODE [[
    file(GLOB_RECURSE _thrift_types
        "${CMAKE_INSTALL_PREFIX}/lib/python3/site-packages/*/thrift_types.py")
    foreach(_f ${_thrift_types})
        get_filename_component(_dir "${_f}" DIRECTORY)
        file(WRITE "${_dir}/types.py" "from .thrift_types import *\n")
        file(WRITE "${_dir}/ttypes.py" "from .thrift_types import *\n")
    endforeach()
    file(GLOB_RECURSE _thrift_clients
        "${CMAKE_INSTALL_PREFIX}/lib/python3/site-packages/*/thrift_clients.py")
    foreach(_f ${_thrift_clients})
        get_filename_component(_dir "${_f}" DIRECTORY)
        file(WRITE "${_dir}/clients.py" "from .thrift_clients import *\n")
    endforeach()
]])
