#!/bin/bash
# Build the qwsim pybind11 module against the repo venv.
# No cmake on this machine; direct gcc/g++ invocation.
#
# Float discipline: -O2, NO -ffast-math, -ffp-contract=off (no FMA fusion)
# => strict IEEE-754 single-precision, same arithmetic as a stock x86-64
#    mvdsv build. See EXTRACTION-NOTES.md.
set -euo pipefail
cd "$(dirname "$0")"

PY=/home/benjamin-adm/rex-ml/.venv/bin/python
# System python3.12 has no -dev headers and sudo is unavailable; use the
# uv-managed CPython 3.12 headers (same cp312 ABI as the venv's interpreter).
PYINC=/home/benjamin-adm/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/include/python3.12
PBINC=$($PY -c "import pybind11; print(pybind11.get_include())")
EXT=$($PY -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")

CFLAGS="-O2 -fPIC -fopenmp -ffp-contract=off -fwrapv -DSERVERONLY -Wall -Wno-unused-variable -Wno-unused-but-set-variable"
mkdir -p build

for f in pmove pmovetst cmodel mathlib md4 shim qwsim_core; do
  gcc $CFLAGS -c csrc/$f.c -o build/$f.o
done

g++ -O2 -fPIC -fopenmp -ffp-contract=off -shared -std=c++17 \
    -I"$PYINC" -I"$PBINC" \
    qwsim_module.cpp build/*.o \
    -o "qwsim$EXT"

echo "built qwsim$EXT"
$PY -c "import sys; sys.path.insert(0,'.'); import qwsim; print('import ok:', qwsim.__doc__)"
