#!/usr/bin/env bash
# Run locally what CI runs, in the same order, and report every failure rather
# than stopping at the first. `set -e` is deliberately not on: a lint failure
# should not hide a test failure, because then fixing the lint reveals the test
# and the loop takes two rounds instead of one.
set -uo pipefail
cd "$(dirname "$0")" || exit 1

PY="${PYTHON:-python}"
LOGS="$(mktemp -d)"
failed=()

run() {
  local name="$1"; shift
  printf '%-22s' "$name"
  if "$@" > "$LOGS/$name.log" 2>&1; then
    echo "ok"
  else
    echo "FAILED"
    failed+=("$name")
  fi
}

run ruff-check "$PY" -m ruff check .
run ruff-format "$PY" -m ruff format --check .
run mypy "$PY" -m mypy
run pytest "$PY" -m pytest -q

if [ "${#failed[@]}" -gt 0 ]; then
  echo
  for name in "${failed[@]}"; do
    echo "--- $name ---"
    tail -40 "$LOGS/$name.log"
  done
  echo
  printf '%d failed: %s\n' "${#failed[@]}" "${failed[*]}"
  exit 1
fi

echo
echo "everything green"
