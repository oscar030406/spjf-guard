#!/usr/bin/env bash
# The grid, one (overlay, level) per process, each started behind the memory gate.
# usage: bash evidence/abandonment_loop/run_grid.sh "0 1 2"   (levels)
set -euo pipefail
cd "$(dirname "$0")/../.."
levels=${1:-"0 1 2"}
for level in $levels; do
  for rep in 0 1 2 3 4; do
    bash evidence/abandonment_loop/gated.sh evidence/abandonment_loop/run_abandon.py run \
      --reps "$rep" --levels "$level" --resume
  done
done
echo "grid done"
