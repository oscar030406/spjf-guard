#!/usr/bin/env bash
# Collection driver.  Every stage of fci_collect.py is resumable (a page already on disk
# is skipped and pages are written atomically), and a long-lived python process on this
# host degrades from ~0.7 s to ~40 s per API call after a few hundred requests while a
# fresh process stays fast.  So each stage is run in bounded restarts instead of once.
#
#   bash run_collect.sh <stage> [seconds-per-attempt] [max-attempts]
set -u
cd "$(dirname "$0")"
STAGE="${1:?stage}"
SLICE="${2:-240}"
TRIES="${3:-40}"
for i in $(seq 1 "$TRIES"); do
  echo "--- $STAGE attempt $i ---"
  timeout "$SLICE" env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME \
    uv run --with requests --with pandas --with pyarrow python fci_collect.py "$STAGE"
  rc=$?
  # 0 = the stage finished; 3 = the process retired itself after FCI_REQ_LIMIT
  # requests; 124 = the outer time slice expired.  Both mean: go round again.
  if [ "$rc" -eq 0 ]; then
    echo "--- $STAGE finished on attempt $i ---"
    exit 0
  fi
  if [ "$rc" -ne 124 ] && [ "$rc" -ne 3 ]; then
    echo "--- $STAGE failed with exit code $rc ---"
    exit "$rc"
  fi
done
echo "--- $STAGE still unfinished after $TRIES attempts ---"
exit 1
