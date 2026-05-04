#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "[sample] mode=t2v is no longer supported by this service."
echo "[sample] Use: bash ${SERVICE_ROOT}/scripts/run_sample_i2v.sh"
exit 1
