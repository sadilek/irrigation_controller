"""Enclosure for the throwaway board: a tray with standoffs and a flat lid.

    uv run python boards/throwaway/enclosure.py [--lid-drop MM]

Coordinates match the board STEP from `make fab`: origin at the board's top-left corner (as drawn
in KiCad), x right, y up (so the board spans y = -height .. 0), board bottom face at z = 0.
The board size and hole positions come from mech.json, the same file layout.py reads.

--lid-drop lowers the lid into the cavity; `make selftest` uses it to prove that the collision
check actually fails when parts overlap.
"""
import argparse
import json
from pathlib import Path

from build123d import Align, Axis, Box, BuildPart, Cylinder, Locations, Mode, Pos, export_step, export_stl, fillet

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "build" / HERE.name / "enclosure"

args = argparse.ArgumentParser()
args.add_argument("--lid-drop", type=float, default=0.0)
args = args.parse_args()

mech = json.loads((HERE / "mech.json").read_text())
W, H, T = (mech["board"][k] for k in ("width", "height", "thickness"))
GAP = mech["clearance_to_enclosure"]
HOLES = [(x, -y) for x, y in mech["mounting_holes"].values()]  # KiCad y down -> model y up

WALL = 2.0
FLOOR = 2.0
STANDOFF = 3.0  # board bottom above the floor: room for solder joints of through-hole parts
HEADROOM = 12.0  # above the board top: pin header 8.5 mm plus a plug
INSERT_D = 4.0  # hole for an M3 heat-set insert
STANDOFF_D = 7.0
SLOT_W, SLOT_H = 10.0, 9.0  # cable opening in the wall next to J1

inner_w, inner_h = W + 2 * GAP, H + 2 * GAP
outer_w, outer_h = inner_w + 2 * WALL, inner_h + 2 * WALL
cx, cy = W / 2, -H / 2
z_floor = -STANDOFF
z_rim = T + HEADROOM

with BuildPart() as base:
    with Locations((cx, cy, z_floor - FLOOR)):
        Box(outer_w, outer_h, z_rim - z_floor + FLOOR, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(base.edges().filter_by(Axis.Z), radius=3.0)
    with Locations((cx, cy, z_floor)):
        Box(inner_w, inner_h, z_rim - z_floor, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    with Locations(*[(x, y, z_floor) for x, y in HOLES]):
        Cylinder(STANDOFF_D / 2, STANDOFF, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Cylinder(INSERT_D / 2, STANDOFF, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    # Cable slot through the left wall, open to the rim, at the height of J1.
    with Locations((-GAP - WALL / 2, -11.5, T + 1.0)):
        Box(WALL + 1.0, SLOT_W, z_rim - T, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

with BuildPart() as lid:
    with Locations((cx, cy, z_rim - args.lid_drop)):
        Box(outer_w, outer_h, 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
    fillet(lid.edges().filter_by(Axis.Z), radius=3.0)
    # Locating lip that drops 2 mm into the cavity.
    with Locations((cx, cy, z_rim - args.lid_drop - 2.0)):
        Box(inner_w - 0.4, inner_h - 0.4, 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN))
        Box(inner_w - 0.4 - 2 * 1.6, inner_h - 0.4 - 2 * 1.6, 2.0, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

OUT.mkdir(parents=True, exist_ok=True)
for name, part in (("base", base.part), ("lid", lid.part)):
    export_step(part, str(OUT / f"{name}.step"))
    export_stl(part, str(OUT / f"{name}.stl"))
    bb = part.bounding_box()
    print(f"enclosure: {name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume / 1000:.1f} cm3 -> build/{HERE.name}/enclosure/{name}.step, .stl")
