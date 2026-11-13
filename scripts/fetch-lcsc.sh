#!/usr/bin/env bash
# Fetch symbol, footprint and STEP model of LCSC parts into lib/lcsc/ (via easyeda2kicad).
#
#   scripts/fetch-lcsc.sh C6186 [C...]
#
# easyeda2kicad writes the absolute output path into the footprint's 3D-model reference. That would
# leak a home directory into the repo and break on every other machine, so the STEP model is embedded
# into the .kicad_mod instead (`pcb embed-step`) and the loose model files are deleted.
# Converted symbols are raw material: check pin names, pin types and the footprint against the
# datasheet before use, and add the part to lib/jlcpcb-parts.csv.
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -gt 0 ] || { echo "usage: $0 <LCSC id>..." >&2; exit 1; }
out="$PWD/lib/lcsc/lcsc"
mkdir -p lib/lcsc
for id in "$@"; do
  log="$(uvx easyeda2kicad@1.0.1 --full --lcsc_id="$id" --output "$out" --overwrite 2>&1)" || { echo "$log" >&2; exit 1; }
  fp="$(printf '%s\n' "$log" | sed -n 's/.*Footprint path: //p')"
  step="$(printf '%s\n' "$log" | sed -n 's/.*3D model path (step): //p')"
  [ -f "$fp" ] || { echo "$log" >&2; echo "no footprint for $id" >&2; exit 1; }
  if [ -f "$step" ]; then
    .tools/bin/pcb embed-step "$fp" "$step"
    # easyeda2kicad often places the model a few tenths of a millimetre off the pads.
    .tools/bin/pcb rectify fix "$fp" >/dev/null || true
  else
    echo "warning: $id has no STEP model" >&2
  fi
  echo "$id: ${fp#$PWD/}"
done
rm -rf "$out.3dshapes"
# easyeda2kicad writes a KiCad 6 era format; `pcb apply` needs KiCad 10 files.
kicad=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
"$kicad" sym upgrade --force "$out.kicad_sym" >/dev/null 2>&1
"$kicad" fp upgrade --force "$out.pretty" >/dev/null 2>&1
if grep -rl "$HOME" lib/lcsc >/dev/null 2>&1; then
  echo "error: absolute paths left in lib/lcsc:" >&2; grep -rl "$HOME" lib/lcsc >&2; exit 1
fi
