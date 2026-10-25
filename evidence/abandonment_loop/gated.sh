#!/usr/bin/env bash
# Run one command after committed memory falls below 76 GB (the shared machine's gate).
# usage: bash evidence/abandonment_loop/gated.sh <python args...>
set -euo pipefail
cd "$(dirname "$0")/../.."
while true; do
  m=$(powershell -NoProfile -Command '$o=Get-CimInstance Win32_OperatingSystem; [math]::Round(($o.TotalVirtualMemorySize-$o.FreeVirtualMemory)/1MB,1)' | tr -d '\r')
  if awk "BEGIN{exit !($m < 76)}"; then break; fi
  echo "$(date +%T) committed ${m} GB >= 76, waiting" >&2
  sleep 120
done
echo "$(date +%T) committed ${m} GB, starting: $*" >&2
env -u PYTHONHOME -u PYTHONPATH -u UV_INTERNAL__PYTHONHOME NUMBA_NUM_THREADS=4 OMP_NUM_THREADS=4 \
  .venv/Scripts/python.exe -u "$@"
