#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
export PYTHONDONTWRITEBYTECODE=1
export UV_CACHE_DIR="$PWD/evidence/lpc_egee/cache/uv"
export UV_PYTHON_INSTALL_DIR="$PWD/evidence/lpc_egee/cache/python"
export TMPDIR="$PWD/evidence/lpc_egee/cache/tmp"
export TEMP="$TMPDIR"
export TMP="$TMPDIR"
mkdir -p "$TMPDIR"
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 uv run --no-project --with numpy --with pandas --with numba --with lightgbm --with scikit-learn python "evidence/lpc_egee/${1:-audit}.py"
