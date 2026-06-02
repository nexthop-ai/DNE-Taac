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
# The wheel is produced by the fbthrift-python manifest, NOT fbthrift —
# getdeps installs each into its own hash-suffixed prefix. Scan
# CMAKE_PREFIX_PATH (set by the getdeps cmake builder with every
# transitive install prefix) for the wheels dir, and fail the configure
# loudly if it's missing instead of silently skipping pip install.
#
# CMAKE_PREFIX_PATH from the environment is `:`-separated (POSIX), but
# CMake `foreach()` iterates `;`-separated lists. Convert here so each
# prefix is a single iteration.
set(FBTHRIFT_WHEELS_DIR "")
string(REPLACE ":" ";" _cmake_prefix_path_list "$ENV{CMAKE_PREFIX_PATH}")
foreach(_prefix IN LISTS _cmake_prefix_path_list)
    file(GLOB _wheel_candidates "${_prefix}/share/thrift/wheels/thrift-*.whl")
    if(_wheel_candidates)
        set(FBTHRIFT_WHEELS_DIR "${_prefix}/share/thrift/wheels")
        break()
    endif()
endforeach()
if(NOT FBTHRIFT_WHEELS_DIR)
    message(FATAL_ERROR
        "Cannot locate the fbthrift-python wheel under any "
        "CMAKE_PREFIX_PATH entry. Expected "
        "<prefix>/share/thrift/wheels/thrift-*.whl from the "
        "fbthrift-python manifest. Without this, `import thrift` fails at "
        "runtime."
    )
endif()
install(CODE "
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -m pip install
            --break-system-packages
            --find-links ${FBTHRIFT_WHEELS_DIR} thrift
    )
")

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
# (which points at <scratch>/installed/taac-<HASH>/) actually places the
# files where expected. An absolute ${Python3_SITELIB} would bypass the
# install prefix and land the files in the host's system Python — outside
# the build's install tree.
install(
    DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/taac
    DESTINATION lib/python3/site-packages
    FILES_MATCHING PATTERN "*.py"
)
