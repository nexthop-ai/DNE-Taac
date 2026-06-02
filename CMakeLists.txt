cmake_minimum_required(VERSION 3.16)
project(taac VERSION 1.0.0 LANGUAGES CXX)

option(TAAC_BUILD_PYTHON_THRIFT "Build Python thrift bindings" ON)

# ---- Find fbthrift (built by getdeps before us) ----
# getdeps sets CMAKE_PREFIX_PATH to include fbthrift's install dir,
# which exposes FBTHRIFT_COMPILER (path to thrift1) and the codegen macros.
find_package(FBThrift CONFIG REQUIRED)

# ---- Load codegen macros (defines add_fbthrift_py_library, etc.) ----
list(APPEND CMAKE_MODULE_PATH
    "${CMAKE_CURRENT_SOURCE_DIR}/build/fbcode_builder/CMake"
)
include(FBThriftPyLibrary)

# ---- Find Python ----
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# ---- Locate FBOSS source dir (fetched by getdeps fboss-thrift-defs, not built) ----
if(NOT FBOSS_THRIFT_SOURCE_DIR)
    if(DEFINED ENV{FBOSS_THRIFT_SOURCE_DIR})
        set(FBOSS_THRIFT_SOURCE_DIR "$ENV{FBOSS_THRIFT_SOURCE_DIR}")
    else()
        execute_process(
            COMMAND ${Python3_EXECUTABLE}
                ${CMAKE_CURRENT_SOURCE_DIR}/build/fbcode_builder/getdeps.py
                show-source-dir fboss-thrift-defs
            OUTPUT_VARIABLE FBOSS_THRIFT_SOURCE_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE
            RESULT_VARIABLE GETDEPS_RESULT
        )
        if(NOT GETDEPS_RESULT EQUAL 0)
            message(FATAL_ERROR
                "Cannot locate FBOSS thrift source directory. "
                "Set -DFBOSS_THRIFT_SOURCE_DIR=<path> or ensure getdeps "
                "fetched fboss-thrift-defs."
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
                --find-links ${FBTHRIFT_WHEELS_DIR} thrift
        )
    ")
endif()

# ---- Install third-party pip dependencies ----
install(CODE "
    execute_process(
        COMMAND ${Python3_EXECUTABLE} -m pip install -r
            ${CMAKE_CURRENT_SOURCE_DIR}/requirements.txt
    )
")

# ---- Install TAAC Python source ----
install(
    DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/taac
    DESTINATION ${Python3_SITELIB}
    FILES_MATCHING PATTERN "*.py"
)
