cmake_minimum_required(VERSION 3.16)
project(taac VERSION 1.0.0 LANGUAGES CXX)

option(TAAC_BUILD_PYTHON_THRIFT "Build Python thrift bindings" ON)

# ---- Register cmake modules shipped with fbthrift ----
# Must happen BEFORE find_package(FBThrift). FBThriftConfig.cmake calls
# find_dependency(Xxhash), which falls back to MODULE mode and needs
# FindXxhash.cmake (+ similar for libiberty, etc.) on CMAKE_MODULE_PATH.
list(APPEND CMAKE_MODULE_PATH
    "${CMAKE_CURRENT_SOURCE_DIR}/build/fbcode_builder/CMake"
)

# ---- Find fbthrift (built by getdeps before us) ----
# getdeps sets CMAKE_PREFIX_PATH to include fbthrift's install dir,
# which exposes FBTHRIFT_COMPILER (path to thrift1) and the codegen macros.
find_package(FBThrift CONFIG REQUIRED)

# ---- Load codegen macros ----
# FBThriftPyLibrary: defines add_fbthrift_py_library (--gen py)
# FBThriftPythonLibrary: defines add_fbthrift_python_library (mstch_python)
include(FBThriftPyLibrary)
include(FBThriftPythonLibrary)

# ---- Find Python ----
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# ---- Locate FBOSS source dir (fetched by getdeps fboss-thrift-defs, not built) ----
# When getdeps drives our build it sets CMAKE_PREFIX_PATH in the environment
# with every transitive install dir, including fboss-thrift-defs-<HASH>/
# (which IS the source tree because that manifest's builder = nop). Search
# those prefixes for a known FBOSS .thrift file to locate the install dir.
if(NOT FBOSS_THRIFT_SOURCE_DIR)
    if(DEFINED ENV{FBOSS_THRIFT_SOURCE_DIR})
        set(FBOSS_THRIFT_SOURCE_DIR "$ENV{FBOSS_THRIFT_SOURCE_DIR}")
    else()
        find_path(FBOSS_THRIFT_SOURCE_DIR
            NAMES "fboss/agent/if/ctrl.thrift"
            PATHS ENV CMAKE_PREFIX_PATH
            NO_DEFAULT_PATH
        )
        if(NOT FBOSS_THRIFT_SOURCE_DIR)
            message(FATAL_ERROR
                "Cannot locate FBOSS thrift source directory. "
                "Set -DFBOSS_THRIFT_SOURCE_DIR=<path> or ensure getdeps "
                "fetched fboss-thrift-defs and CMAKE_PREFIX_PATH points at it."
            )
        endif()
    endif()
endif()
message(STATUS "FBOSS thrift source dir: ${FBOSS_THRIFT_SOURCE_DIR}")

# ---- Compile thrift -> Python bindings ----
if(TAAC_BUILD_PYTHON_THRIFT)
    add_subdirectory(thrift)
endif()

# ---- Install thrift-python wheel (runtime imported by TAAC) ----
find_path(FBTHRIFT_WHEELS_DIR
    NAMES "thrift"
    PATHS "${FBThrift_DIR}/../../../share/thrift/wheels"
    NO_DEFAULT_PATH
)
if(FBTHRIFT_WHEELS_DIR)
    install(CODE "
        execute_process(
            COMMAND ${Python3_EXECUTABLE} -m pip install
                --break-system-packages
                --find-links ${FBTHRIFT_WHEELS_DIR} thrift
        )
    ")
endif()

# ---- Install third-party pip dependencies ----
install(CODE "
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -m pip install
            --break-system-packages
            -r ${CMAKE_CURRENT_SOURCE_DIR}/requirements.txt
    )
")

# ---- Install TAAC Python source ----
# Destination is RELATIVE to CMAKE_INSTALL_PREFIX so getdeps' --prefix
# (which points at /scratch/installed/taac-<HASH>/) actually places the
# files where expected. An absolute ${Python3_SITELIB} would land the
# files in the container's system Python and they'd disappear on exit.
install(
    DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/taac
    DESTINATION lib/python3/site-packages
    FILES_MATCHING PATTERN "*.py"
)
