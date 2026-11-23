#!/usr/bin/env bash
set -euo pipefail

# RAM-safe Threadon test runner (16 GB friendly).
# - Runs sequentially (no xdist/parallel pytest).
# - Caps virtual memory per process to reduce OOM/desktop crashes.
# - Disables pytest plugin autoload for reproducibility.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${PYTHONPATH:-}:$ROOT/compiler"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"

# 2 GiB virtual address space per process; adjust if needed.
ULIMIT_V_KB="${THREADON_ULIMIT_V_KB:-2000000}"
ulimit -v "$ULIMIT_V_KB"

if [ "$#" -eq 0 ]; then
  set -- -q tests/test_gen_docs.py tests/test_docs_examples.py tests/test_purity_exhaustive.py
fi

echo "[test_safe] cwd=$ROOT ulimit_v=${ULIMIT_V_KB}KB args=$*" >&2
exec python3 -m pytest "$@"
