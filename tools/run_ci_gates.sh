#!/usr/bin/env bash
# REPO-ONLY TOOL
# =============================================================
# CI/PR Lite gates runner for Linux/macOS (bash)
#
# Design goals
# - Make the gate workflow hard to misuse for beginners.
# - Fail-fast: any failure stops the remaining steps.
# - Dependency-free: only Python + pip.
#
# Exit codes (aligned with docs/reference/reference.yaml)
# - 0: PASS
# - 2: FAIL  (contract/gate violation, test failures)
# - 3: ERROR (environment/setup failure)
#
# Usage:
#   bash tools/run_ci_gates.sh
#   bash tools/run_ci_gates.sh --with-embed
#   bash tools/run_ci_gates.sh --no-install
#   bash tools/run_ci_gates.sh --venv .venv_ci

set -o nounset
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 3

VENV='.venv_ci'
WITH_EMBED=0
NO_INSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-embed)
      WITH_EMBED=1
      shift
      ;;
    --no-install)
      NO_INSTALL=1
      shift
      ;;
    --venv)
      if [[ $# -lt 2 ]]; then
        echo "[FAIL] --venv requires a value"
        exit 2
      fi
      VENV="$2"
      shift 2
      ;;
    *)
      echo "[FAIL] unknown arg: $1"
      echo "Usage: bash tools/run_ci_gates.sh [--venv .venv_ci] [--no-install] [--with-embed]"
      exit 2
      ;;
  esac
done

find_base_python() {
  # Prefer explicit minor versions when available.
  if command -v python3.12 >/dev/null 2>&1; then echo python3.12; return 0; fi
  if command -v python3.11 >/dev/null 2>&1; then echo python3.11; return 0; fi
  if command -v python3 >/dev/null 2>&1; then echo python3; return 0; fi
  if command -v python >/dev/null 2>&1; then echo python; return 0; fi
  echo ""
  return 0
}

normalize_rc() {
  # Map common exit codes to {0,2,3}.
  local rc="$1"
  if [[ "$rc" -eq 0 ]]; then echo 0; return 0; fi
  if [[ "$rc" -eq 2 ]]; then echo 2; return 0; fi
  if [[ "$rc" -eq 3 ]]; then echo 3; return 0; fi
  if [[ "$rc" -eq 1 ]]; then echo 2; return 0; fi
  if [[ "$rc" -ge 4 ]]; then echo 3; return 0; fi
  echo 2
}

run_gate() {
  set +e
  "$@"
  local rc=$?
  set -e
  local norm
  norm="$(normalize_rc "$rc")"
  return "$norm"
}

set -o errexit

BASEPY="$(find_base_python)"
if [[ -z "$BASEPY" ]]; then
  echo "[ERROR] cannot find a base Python to create venv."
  echo "        Install Python 3.11+ and ensure python3/python is on PATH."
  exit 3
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[INFO] creating venv $VENV using: $BASEPY"
  "$BASEPY" -m venv "$VENV" || exit 3
fi

PY="$VENV/bin/python"
echo "[INFO] python = $PY"

# 1) Preflight + repo-structure gates (stop before any pip install)
run_gate "$PY" tools/check_pyproject_preflight.py --ascii-only || exit "$?"
run_gate "$PY" tools/gen_tools_wrappers.py --check || exit "$?"
run_gate "$PY" tools/check_tools_layout.py --mode fail || exit "$?"
run_gate "$PY" tools/check_exit_code_contract.py --root . || exit "$?"
run_gate "$PY" tools/validate_review_spec.py --root . || exit "$?"

# 2) (Optional) install/update deps
if [[ "$NO_INSTALL" -eq 0 ]]; then
  "$PY" -m pip install -U pip || exit 3
  "$PY" -m pip install -e ".[ci]" || exit 3
  if [[ "$WITH_EMBED" -eq 1 ]]; then
    "$PY" -m pip install -e ".[embed]" || exit 3
  fi
else
  echo "[INFO] --no-install: skip pip install steps"
fi

# 3) Run PR/CI Lite gates
run_gate "$PY" tools/check_cli_entrypoints.py || exit "$?"
run_gate "$PY" tools/check_md_refs_contract.py || exit "$?"
run_gate "$PY" tools/check_readme_code_sync.py --root . || exit "$?"
run_gate "$PY" -m pytest -q || exit "$?"

echo "[PASS] CI/PR Lite gates OK"
exit 0
