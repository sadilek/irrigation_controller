#!/usr/bin/env bash
# Prove that the schematic comparison can fail: rename one net label in the arranged schematic and
# expect the Zener build to report the difference. The schematic is restored afterwards.
#   tools/selftest-schematic.sh <board> <pcb command...>
set -euo pipefail
board="$1"; shift
cd "$(dirname "$0")/../boards/$board"
sch="eda/$board.kicad_sch"
[ -f schematic.py ] || { echo "selftest: $board has no schematic.py"; exit 1; }
backup="$(mktemp)"
cp "$sch" "$backup"
trap 'cp "$backup" "$sch"; rm -f "$backup"' EXIT
"$@" build -D warnings "$board.zen" >/dev/null 2>&1 || { echo "selftest: schematic differs from the source before the test"; exit 1; }
label="$(grep -m1 -o '(label "[^"]*"' "$sch")"
python3 - "$sch" "$label" <<'PY'
import sys
path, label = sys.argv[1:]
text = open(path).read()
open(path, "w").write(text.replace(label, label[:-1] + '_X"', 1))
PY
if "$@" build -D warnings "$board.zen" >/dev/null 2>&1; then
  echo "selftest: changed schematic NOT detected"; exit 1
fi
echo "selftest: changed schematic detected as expected"
