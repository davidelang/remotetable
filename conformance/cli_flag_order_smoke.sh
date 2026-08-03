#!/usr/bin/env bash
# Ensure global flags work before and after the subcommand.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CLI="$ROOT/scripts/remotetable"
FIX="$ROOT/conformance/fixtures/mock_book.json"
export PYTHONPATH="$ROOT/python${PYTHONPATH:+:$PYTHONPATH}"

out1=$("$CLI" --backend mock --fixture "$FIX" test-connection)
out2=$("$CLI" test-connection --backend mock --fixture "$FIX")
echo "$out1" | grep -q '"ok": true'
echo "$out2" | grep -q '"ok": true'
echo "PASS cli flag order (before and after subcommand)"
