# ============================================================================
# TAAC Thrift -> Python Codegen
# ============================================================================
# Two sources of .thrift files:
#   1. TAAC-owned: ${TAAC_THRIFT_DIR} (thrift/ directory in THIS repo)
#   2. FBOSS:     ${FBOSS_THRIFT_DIR} (fetched by getdeps fboss-thrift-defs)
# ============================================================================

set(TAAC_THRIFT_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(FBOSS_THRIFT_DIR "${FBOSS_THRIFT_SOURCE_DIR}")

# Include paths for thrift "include" statement resolution across both sources
set(THRIFT_INCLUDE_DIRS
    "${TAAC_THRIFT_DIR}"
    "${FBOSS_THRIFT_DIR}"
)

# ============================================================================
# SECTION A: Common / Shared (from FBOSS)
# ============================================================================

# facebook.network.Address
add_fbthrift_py_library(
    network_address_py
    "${FBOSS_THRIFT_DIR}/common/network/if/Address.thrift"
    NAMESPACE "facebook.network.Address"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

# ============================================================================
# SECTION B: FBOSS Thrift (from fetched source)
# ============================================================================

add_fbthrift_py_library(
    mpls_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/mpls.thrift"
    NAMESPACE "neteng.fboss.mpls"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    fboss_common_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/if/fboss_common.thrift"
    NAMESPACE "neteng.fboss.fboss_common"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    fboss_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/fboss.thrift"
    NAMESPACE "neteng.fboss"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    common_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/common.thrift"
    NAMESPACE "neteng.fboss.common"
    OPTIONS json
    DEPENDS mpls_py network_address_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    switch_config_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/switch_config.thrift"
    NAMESPACE "neteng.fboss.switch_config"
    OPTIONS json
    DEPENDS common_py fboss_common_py mpls_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    ctrl_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/ctrl.thrift"
    NAMESPACE "neteng.fboss.ctrl"
    OPTIONS json
    DEPENDS common_py fboss_py mpls_py switch_config_py network_address_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    hw_ctrl_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/if/hw_ctrl.thrift"
    NAMESPACE "neteng.fboss.hw_ctrl"
    OPTIONS json
    DEPENDS ctrl_py common_py fboss_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    hardware_stats_py
    "${FBOSS_THRIFT_DIR}/fboss/agent/hw/hardware_stats.thrift"
    NAMESPACE "neteng.fboss.hardware_stats"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    prbs_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/prbs.thrift"
    NAMESPACE "neteng.fboss.prbs"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    link_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/link.thrift"
    NAMESPACE "neteng.fboss.link"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    transceiver_py
    "${FBOSS_THRIFT_DIR}/fboss/qsfp_service/if/transceiver.thrift"
    NAMESPACE "neteng.fboss.transceiver"
    OPTIONS json
    DEPENDS prbs_py link_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    phy_py
    "${FBOSS_THRIFT_DIR}/fboss/lib/phy/phy.thrift"
    NAMESPACE "neteng.fboss.phy"
    OPTIONS json
    DEPENDS prbs_py link_py transceiver_py switch_config_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    fsdb_py
    "${FBOSS_THRIFT_DIR}/fboss/fsdb/if/fsdb.thrift"
    NAMESPACE "neteng.fboss.fsdb"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

# ============================================================================
# SECTION C: TAAC-Owned Thrift (from this repo)
# ============================================================================

add_fbthrift_py_library(
    qosdb_cos_py
    "${TAAC_THRIFT_DIR}/qosdb/Cos.thrift"
    NAMESPACE "neteng.qosdb.Cos"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    ixia_py
    "${TAAC_THRIFT_DIR}/ixia/ixia.thrift"
    NAMESPACE "ixia"
    OPTIONS json
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    health_check_py
    "${TAAC_THRIFT_DIR}/taac/health_check.thrift"
    NAMESPACE "taac.health_check.health_check"
    OPTIONS json
    DEPENDS qosdb_cos_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

add_fbthrift_py_library(
    test_as_a_config_py
    "${TAAC_THRIFT_DIR}/taac/test_as_a_config.thrift"
    NAMESPACE "taac.taac"
    OPTIONS json
    DEPENDS health_check_py ixia_py
    THRIFT_INCLUDE_DIRECTORIES ${THRIFT_INCLUDE_DIRS}
)

# ============================================================================
# SECTION D: Install generated Python to site-packages
# ============================================================================

install(
    DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/gen-py/"
    DESTINATION "${Python3_SITELIB}"
    FILES_MATCHING PATTERN "*.py"
)
