"""Enclosure for the valve node: a sealed box that lies in a valve box in the ground.

    uv run python boards/valve-node/enclosure.py [--no-views] [--lid-drop MM]

Parts: base, lid, gasket, and four identical cable entries, each with a nut, a pressure washer and
a soft insert that seals around the cable. What every dimension is for: docs/valve-node-enclosure.md.

Coordinates match the board STEP: origin at the board's top-left corner (as drawn in KiCad), x
right, y up (the board spans y = -height .. 0), board bottom face at z = 0. Board size, mounting
holes and connector positions come from mech.json, the same file the layout reads.

Written to build/valve-node/:
  enclosure/*.step   every part where it sits in the assembly, nuts hand-tight
  print/*.stl        one of each printed part, lying the way it is printed
  envelope.step      the board as mech.json describes it, with connectors as blocks: stands in
                     for the board STEP in `make collide` until the layout exists
  views/*.png        pictures

--lid-drop lowers the lid into the box; `make selftest` uses it to prove that the collision check
fails when the lid hits a connector.
"""
import argparse
import json
import math
import sys
import warnings
from pathlib import Path

from build123d import (
    Align, Axis, Box, BuildPart, BuildSketch, Circle, Cone, Cylinder, Location, Locations, Mode, Plane, Polygon, Pos,
    RectangleRounded, Rot, chamfer, export_step, export_stl, extrude,
)

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools"))
from printthread import PITCH, external_thread, internal_thread  # noqa: E402

warnings.filterwarnings("ignore", message="Boolean operation unable to clean")

args = argparse.ArgumentParser()
args.add_argument("--lid-drop", type=float, default=0.0)
args.add_argument("--no-views", action="store_true")
args = args.parse_args()

mech = json.loads((HERE / "mech.json").read_text())
W, H, T = (mech["board"][k] for k in ("width", "height", "thickness"))
BOARD_R = mech["board"]["corner_radius"]
GAP = mech["clearance_to_enclosure"]  # board edge to the long walls
HOLES = [(x, -y) for x, y in mech["mounting_holes"].values()]  # KiCad y down -> model y up
CONNECTORS = {k: v for k, v in mech["connectors"].items() if not k.startswith("_")}

# --- What the owner still has to measure (assumed until then) -----------------------------------
BUS_CABLE_D = 6.0  # outer diameter of the buried bus cable
VALVE_WIRE_D = 2.2  # outer diameter of one valve wire, with insulation
SENSOR_CABLE_D = 4.5  # outer diameter of a moisture sensor cable
PLUG_BORE_D = 15.5  # smallest round hole a crimped RJ45 plug passes through (11.7 x 8.1 mm body plus latch)

# --- Box ----------------------------------------------------------------------------------------
WALL = 3.0
FLOOR = 3.0
STANDOFF = 5.0  # board bottom above the floor; mech.json allows 3.5 mm of pins below the board
CABLE_SPACE = 30.0  # between a board end and the wall: plug, fingers, a little slack
RIM_Z = 22.0  # top of the base; set by the cable entries, which have to end below the flange's top
CORNER_R = 4.0  # outer corner radius of the box body
FLANGE = 5.5  # how far the rim stands out beyond the wall
FLANGE_T = 4.0  # thickness of the rim before its 45 degree underside starts
LID_T = 4.0

# Gasket: a flat printed ring in a groove, compressed by a narrow ridge under the lid. The lid
# stops on the rim, so the compression is set by geometry and not by how hard a screw is turned.
GROOVE_IN = 2.0  # from the cavity wall to the groove
GROOVE_W = 3.0
GROOVE_DEPTH = 2.5
GASKET_W = 2.6
GASKET_H = 2.0
TONGUE_W = 1.2
TONGUE_H = 1.0  # reaches 0.5 mm into the gasket
LIP_H = 3.0  # locating rim under the lid, inside the cavity
LIP_W = 1.6
LIP_PLAY = 0.4

# Lid screws: M3 into heat-set inserts, outside the gasket so that no screw hole leads inside.
SCREW_OFFSET = 8.0  # screw axis from the cavity wall
SCREWS_PER_SIDE = 4
EAR_R = 4.5
EAR_T = 9.0  # vertical part of an ear; below it a 45 degree slope back to the wall
INSERT_HOLE_D = 4.0  # hole for an M3 heat-set insert (4.6 mm outer diameter, 5.7 mm long)
INSERT_HOLE_DEPTH = 7.5
SCREW_CLEAR_D = 3.4
STANDOFF_D = 8.0
STANDOFF_HOLE_DEPTH = 6.5

# --- Cable entry --------------------------------------------------------------------------------
# Measured along the entry's axis from the inside face of the wall, outwards ("s").
ENTRY_Z = T + 7.0  # axis height: middle of the plug opening of the bus jack
THREAD_D = 26.4
NECK_END = WALL + 7.0  # plain neck, so the nut stays clear of the rim
BOSS_END = NECK_END + 11.0  # tip of the threaded part
SEAT_START = 9.5
SEAT_SLOPE = 0.16  # radius per length: a cone of 9 degrees half angle
SEAT_R_TIP = 9.6  # seat radius at the tip of the boss
INSERT_START = 11.0  # where the small end of the insert sits when the nut is hand-tight
SQUEEZE = 1.5  # the insert stands this far out of the boss; tightening the nut pushes it in
WASHER_T = 2.0
WASHER_D = 23.6
NUT_D = 33.0
NUT_WALL = 3.0  # end wall
NUT_THREAD = 12.0
SLIT_W = 0.4

x0, x1 = -CABLE_SPACE, W + CABLE_SPACE  # cavity
y0, y1 = -H - GAP, GAP
z_floor = -STANDOFF
z_bottom = z_floor - FLOOR
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
inner_r = CORNER_R - WALL
ZMIN = (Align.CENTER, Align.CENTER, Align.MIN)


def slab(grow: float, z_from: float, z_to: float):
    """The cavity's outline grown by `grow` (negative: shrunk), as a solid between two heights."""
    with BuildPart() as p:
        with BuildSketch(Plane.XY.offset(z_from)):
            with Locations((cx, cy)):
                RectangleRounded(x1 - x0 + 2 * grow, y1 - y0 + 2 * grow, max(inner_r + grow, 0.2))
        extrude(amount=z_to - z_from)
    return p.part


def ring(grow_in: float, grow_out: float, z_from: float, z_to: float):
    return slab(grow_out, z_from, z_to) - slab(grow_in, z_from - 0.01, z_to + 0.01)


def screw_points():
    xs = [x0 + 8 + i * (x1 - x0 - 16) / (SCREWS_PER_SIDE - 1) for i in range(SCREWS_PER_SIDE)]
    return [(x, y1 + SCREW_OFFSET, 1) for x in xs] + [(x, y0 - SCREW_OFFSET, -1) for x in xs]


def ear(x: float, y: float, side: int, z_from: float, z_to: float, sloped: bool):
    """A tab for one lid screw: a round end joined to the wall. `side` is +1 on the +y wall, -1 on the other."""
    wall_y = y - side * (SCREW_OFFSET + WALL)  # outer face of the wall
    reach = abs(y - wall_y)
    with BuildPart() as p:
        with BuildSketch(Plane.XY.offset(z_from)):
            with Locations((x, y)):
                Circle(EAR_R)
            with Locations((x, (y + wall_y) / 2 - side * 0.5)):
                RectangleRounded(2 * EAR_R, reach + 1.0, 0.2)
        extrude(amount=z_to - z_from)
        if sloped:
            # Cut away everything below a 45 degree plane that rises from the wall: prints without support.
            drop = reach + EAR_R
            with BuildSketch(Plane.YZ.offset(x - EAR_R - 1)):
                Polygon(
                    (wall_y, z_to - EAR_T - drop), (wall_y + side * (drop + 1), z_to - EAR_T + 1),
                    (wall_y + side * (drop + 1), z_from - 1), (wall_y, z_from - 1),
                    align=None,
                )
            extrude(amount=2 * EAR_R + 2, mode=Mode.SUBTRACT)
    return p.part


def entry_frame(wall: str, y: float) -> Location:
    """Local frame of a cable entry: origin on the inside face of the wall, z pointing outwards."""
    if wall == "left":
        return Location(Plane(origin=(x0, y, ENTRY_Z), x_dir=(0, 1, 0), z_dir=(-1, 0, 0)))
    return Location(Plane(origin=(x1, y, ENTRY_Z), x_dir=(0, -1, 0), z_dir=(1, 0, 0)))


def seat_r(s: float) -> float:
    return SEAT_R_TIP - SEAT_SLOPE * (BOSS_END - s)


def entry_boss():
    """What an entry adds to the wall (in the entry's frame)."""
    neck = Cylinder(THREAD_D / 2, NECK_END, align=ZMIN)
    return neck + Pos(0, 0, NECK_END) * external_thread(THREAD_D, BOSS_END - NECK_END)


def entry_bore():
    """What an entry removes: a bore the plug passes through, widening into the conical seat."""
    bore = Pos(0, 0, -1) * Cylinder(PLUG_BORE_D / 2, SEAT_START + 1.5, align=ZMIN)
    seat = Pos(0, 0, SEAT_START) * Cone(seat_r(SEAT_START), seat_r(BOSS_END + 0.5), BOSS_END + 0.5 - SEAT_START, align=ZMIN)
    return bore + seat


# Hole patterns of the inserts: (diameter, [(u, v), ...], slit). A slit lets the insert go around a
# cable that already carries a plug; wires with free ends are pushed through closed holes.
PATTERNS = {
    "bus": (BUS_CABLE_D, [(0, 0)], True),
    "valve-2": (VALVE_WIRE_D, [(-2.5, 0), (2.5, 0)], False),
    "valve-4": (VALVE_WIRE_D, [(-2.5, -2.5), (2.5, -2.5), (-2.5, 2.5), (2.5, 2.5)], False),
    "sensor": (SENSOR_CABLE_D, [(0, 0)], False),
    "blank": (0, [], False),
}


def holes(pattern: str, squeeze: float, z_from: float, length: float, slot: bool):
    """Cutter for a hole pattern. `squeeze` < 0 makes the holes smaller than the cable (insert), > 0 larger (washer)."""
    d, points, slit = PATTERNS[pattern]
    cutter = None
    for u, v in points:
        c = Pos(u, v, z_from - 1) * Cylinder((d + squeeze) / 2, length + 2, align=ZMIN)
        cutter = c if cutter is None else cutter + c
    if slit:
        width = (d + squeeze) if slot else SLIT_W  # washer: a slot as wide as the hole; insert: a cut
        cutter = cutter + Pos(0, 10, z_from - 1) * Box(width, 20, length + 2, align=ZMIN)
    return cutter


def insert(pattern: str):
    """Soft cone that the nut pushes into the seat (hand-tight position)."""
    length = BOSS_END + SQUEEZE - INSERT_START
    body = Pos(0, 0, INSERT_START) * Cone(seat_r(INSERT_START), seat_r(INSERT_START + length), length, align=ZMIN)
    cutter = holes(pattern, -0.2, INSERT_START, length, slot=False)
    return body - cutter if cutter is not None else body


def washer(pattern: str):
    """Stiff disc between nut and insert: the nut's opening is as large as the plug, the insert needs support across it."""
    z = BOSS_END + SQUEEZE
    body = Pos(0, 0, z) * Cylinder(WASHER_D / 2, WASHER_T, align=ZMIN)
    cutter = holes(pattern, 0.6, z, WASHER_T, slot=True)
    return body - cutter if cutter is not None else body


def nut():
    """Hand-tight position. The skirt starts a whole number of pitches after the boss thread, so both threads are in phase."""
    start = NECK_END + PITCH
    assert abs(start + NUT_THREAD - (BOSS_END + SQUEEZE + WASHER_T)) < 1e-6, "nut does not close on the washer"
    body = Pos(0, 0, start) * internal_thread(THREAD_D, NUT_THREAD, NUT_D)
    end_wall = Pos(0, 0, start + NUT_THREAD) * (Cylinder(NUT_D / 2, NUT_WALL, align=ZMIN) - Cylinder(PLUG_BORE_D / 2, NUT_WALL, align=ZMIN))
    body = body + end_wall
    for i in range(12):  # grip flutes
        a = math.radians(i * 30)
        body = body - Pos((NUT_D / 2 + 0.7) * math.cos(a), (NUT_D / 2 + 0.7) * math.sin(a), start - 1) * Cylinder(1.5, NUT_THREAD + NUT_WALL + 2, align=ZMIN)
    return body


# --- Entries: two bus cables on the left wall, valve wires and sensor cable on the right ----------
bus_y = sorted((-CONNECTORS[name]["at"][1] for name in ("J_IN", "J_OUT")), reverse=True)
ENTRIES = [
    ("left", bus_y[0], "bus"),
    ("left", bus_y[1], "bus"),
    ("right", bus_y[0], "blank"),  # logic side of the board: moisture sensor, closed with a blank until one is fitted
    ("right", bus_y[1], "valve-4"),  # 24 VAC side of the board: valve wires
]

# --- Base ---------------------------------------------------------------------------------------
base = slab(WALL, z_bottom, RIM_Z)
with BuildPart() as flange:
    with BuildSketch(Plane.XY.offset(RIM_Z - FLANGE_T - FLANGE)):
        with Locations((cx, cy)):
            RectangleRounded(x1 - x0 + 2 * (WALL + FLANGE), y1 - y0 + 2 * (WALL + FLANGE), CORNER_R + FLANGE)
    extrude(amount=FLANGE_T + FLANGE)
    chamfer(flange.edges().group_by(Axis.Z)[0], length=FLANGE - 0.01)
base = base + flange.part
for x, y, side in screw_points():
    base = base + ear(x, y, side, z_bottom + 1, RIM_Z, sloped=True)
for wall, y, _ in ENTRIES:
    base = base + entry_frame(wall, y) * entry_boss()
base = base - slab(0, z_floor, RIM_Z + 1)
for wall, y, _ in ENTRIES:
    base = base - entry_frame(wall, y) * entry_bore()
base = base - ring(GROOVE_IN, GROOVE_IN + GROOVE_W, RIM_Z - GROOVE_DEPTH, RIM_Z + 1)
for x, y, _ in screw_points():
    base = base - Pos(x, y, RIM_Z - INSERT_HOLE_DEPTH) * Cylinder(INSERT_HOLE_D / 2, INSERT_HOLE_DEPTH + 1, align=ZMIN)
for x, y in HOLES:
    base = base + Pos(x, y, z_floor) * Cylinder(STANDOFF_D / 2, STANDOFF, align=ZMIN)
for x, y in HOLES:
    base = base - Pos(x, y, -STANDOFF_HOLE_DEPTH) * Cylinder(INSERT_HOLE_D / 2, STANDOFF_HOLE_DEPTH + 1, align=ZMIN)

# --- Lid ----------------------------------------------------------------------------------------
lid_z = RIM_Z - args.lid_drop
lid = slab(WALL + FLANGE, lid_z, lid_z + LID_T)
for x, y, side in screw_points():
    lid = lid + ear(x, y, side, lid_z, lid_z + LID_T, sloped=False)
tongue_in = GROOVE_IN + (GROOVE_W - TONGUE_W) / 2
lid = lid + ring(tongue_in, tongue_in + TONGUE_W, lid_z - TONGUE_H, lid_z + 0.01)
lid = lid + ring(-LIP_PLAY - LIP_W, -LIP_PLAY, lid_z - LIP_H, lid_z + 0.01)
for x, y, _ in screw_points():
    lid = lid - Pos(x, y, lid_z - 1) * Cylinder(SCREW_CLEAR_D / 2, LID_T + 2, align=ZMIN)

gasket_in = GROOVE_IN + (GROOVE_W - GASKET_W) / 2
gasket = ring(gasket_in, gasket_in + GASKET_W, RIM_Z - GROOVE_DEPTH, RIM_Z - GROOVE_DEPTH + GASKET_H)

# --- Entry parts in place ---------------------------------------------------------------------------
one_nut = nut()
nuts = [entry_frame(wall, y) * one_nut for wall, y, _ in ENTRIES]
washers = [entry_frame(wall, y) * washer(p) for wall, y, p in ENTRIES]
inserts = [entry_frame(wall, y) * insert(p) for wall, y, p in ENTRIES]


def compound(shapes):
    out = shapes[0]
    for s in shapes[1:]:
        out = out + s
    return out


# --- Board envelope -------------------------------------------------------------------------------
# Connector bodies in footprint coordinates (x0, x1, y0, y1, height above the board, pin length below).
BODIES = {
    "J_IN": (-7.87, 7.87, -6.49, 8.51, 13.2, 3.3),  # Amphenol RJHSE-5080
    "J_OUT": (-7.87, 7.87, -6.49, 8.51, 13.2, 3.3),
    "OUT1.J": (-5.08, 5.08, -1.3, 11.16, 8.4, 3.5),  # KF2EDGR-5.08-2P
    "OUT2.J": (-5.08, 5.08, -1.3, 11.16, 8.4, 3.5),
    "J_MOIST": (-2.6, 10.22, -1.2, 8.0, 7.25, 3.5),  # KF2EDGR-3.81-3P on the Phoenix MC 1,5/3-G-3.81 pattern
}


def to_model(name: str, lx: float, ly: float):
    """Footprint coordinates -> model coordinates, with KiCad's counter-clockwise rotation."""
    c = CONNECTORS[name]
    a = math.radians(c["rotation"])
    kx = c["at"][0] + lx * math.cos(a) + ly * math.sin(a)
    ky = c["at"][1] - lx * math.sin(a) + ly * math.cos(a)
    return kx, -ky


def connector_block(name: str):
    lx0, lx1, ly0, ly1, height, pins = BODIES[name]
    (ax, ay), (bx, by) = to_model(name, lx0, ly0), to_model(name, lx1, ly1)
    body = Pos(min(ax, bx), min(ay, by), T) * Box(abs(bx - ax), abs(by - ay), height, align=Align.MIN)
    (px, py), (qx, qy) = to_model(name, lx0, -2.0), to_model(name, lx1, 4.5)  # pin field, generous
    below = Pos(min(px, qx), min(py, qy), -pins) * Box(abs(qx - px), abs(qy - py), pins, align=Align.MIN)
    return body, below


with BuildPart() as board_plate:
    with BuildSketch():
        with Locations((W / 2, -H / 2)):
            RectangleRounded(W, H, BOARD_R)
        with Locations(*HOLES):
            Circle(1.6, mode=Mode.SUBTRACT)
    extrude(amount=T)
blocks = [connector_block(name) for name in BODIES]
envelope = [board_plate.part] + [b for pair in blocks for b in pair]

# --- Output ---------------------------------------------------------------------------------------
BUILD = REPO / "build" / HERE.name
for sub in ("enclosure", "print", "views"):
    (BUILD / sub).mkdir(parents=True, exist_ok=True)

assembly = {
    "base": base, "lid": lid, "gasket": gasket,
    "nuts": compound(nuts), "washers": compound(washers), "inserts": compound(inserts),
}
for name, part in assembly.items():
    if not part.is_valid:
        sys.exit(f"enclosure: {name} is not a valid solid")
    export_step(part, str(BUILD / "enclosure" / f"{name}.step"))
    bb = part.bounding_box()
    print(f"enclosure: {name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume / 1000:.1f} cm3")
export_step(compound(envelope), str(BUILD / "envelope.step"))

# Printed parts, each lying the way it is printed. Material and count per enclosure in the name.
flip = Rot(180, 0, 0)
PRINT = {
    "base": base,
    "lid": flip * lid,  # top face on the bed, gasket ridge up
    "gasket-tpu": gasket,
    "nut-4x": flip * one_nut,  # end wall on the bed, thread axis upright
}
for pattern in PATTERNS:
    PRINT[f"insert-{pattern}-tpu"] = flip * insert(pattern)  # large end on the bed
    PRINT[f"washer-{pattern}"] = washer(pattern)
if not args.lid_drop:
    for name, part in PRINT.items():
        bb = part.bounding_box()
        export_stl(Pos(-bb.center().X, -bb.center().Y, -bb.min.Z) * part, str(BUILD / "print" / f"{name}.stl"), tolerance=0.03, angular_tolerance=0.3)
    print(f"enclosure: {len(assembly)} STEP files -> build/{HERE.name}/enclosure/, {len(PRINT)} STL files -> build/{HERE.name}/print/")

outer = base.bounding_box()
print(f"enclosure: outside {outer.size.X:.0f} x {outer.size.Y:.0f} x {outer.size.Z + LID_T:.0f} mm without nuts, "
      f"{outer.size.X + 2 * (NECK_END + PITCH + NUT_THREAD + NUT_WALL - BOSS_END):.0f} mm long with nuts; "
      f"inside {x1 - x0:.0f} x {y1 - y0:.0f} x {RIM_Z - z_floor:.0f} mm")

# --- Views ----------------------------------------------------------------------------------------
if not args.no_views and not args.lid_drop:
    from render3d import render  # noqa: E402

    BODY, LID, SOFT, NUT, WASHER = (92, 98, 108), (150, 158, 170), (236, 120, 40), (60, 64, 72), (205, 210, 216)
    PCB, PART, CABLE = (40, 130, 70), (40, 40, 44), (120, 150, 190)
    board_items = [(board_plate.part, PCB)] + [(b, PART) for b, _ in blocks]
    entry_items = [(n, NUT) for n in nuts] + [(w, WASHER) for w in washers] + [(i, SOFT) for i in inserts]
    cables = [entry_frame("left", y) * Pos(0, 0, -CABLE_SPACE + 9) * Cylinder(BUS_CABLE_D / 2, 75, align=ZMIN) for _, y, p in ENTRIES if p == "bus"]
    plugs = [Pos(-9.5, y - 5.85, ENTRY_Z - 4) * Box(9.5, 11.7, 8.1, align=Align.MIN) for _, y, p in ENTRIES if p == "bus"]
    cable_items = [(c, CABLE) for c in cables] + [(p, (225, 225, 225)) for p in plugs]

    def cut(items, keep):
        out = []
        for shape, colour in items:
            part = shape & keep
            if part is not None and part.volume > 1e-6:
                out.append((part, colour))
        return out

    V = BUILD / "views"
    render([(base, BODY), (lid, LID)] + entry_items + cable_items, V / "closed.png", view=(-1.0, -1.3, 0.9))
    render([(base, BODY), (gasket, SOFT)] + entry_items + board_items + cable_items, V / "open.png", view=(-0.8, -1.1, 1.3))
    render([(base, BODY), (gasket, SOFT)] + entry_items + board_items + cable_items, V / "top.png", view=(0, 0, 1), up=(0, 1, 0))

    # Section along a bus cable: everything behind the plane through the entry axis.
    y_cut = bus_y[1]
    behind = Pos(cx, y_cut + 100, 0) * Box(400, 200, 200)
    everything = [(base, BODY), (lid, LID), (gasket, SOFT)] + entry_items + board_items + cable_items
    render(cut(everything, behind), V / "section.png", view=(0, -1, 0), size=(1600, 520))
    near = Pos(x0 - 5, y_cut + 100, ENTRY_Z) * Box(62, 200, 60)
    render(cut(everything, near), V / "section-entry.png", view=(0, -1, 0), size=(1600, 1100))

    # One entry taken apart, seen from outside.
    frame = entry_frame("left", bus_y[0])
    apart = [
        (frame * Pos(0, 0, 12) * insert("bus"), SOFT), (frame * Pos(0, 0, 22) * washer("bus"), WASHER),
        (frame * Pos(0, 0, 42) * one_nut, NUT),
    ]
    keep = Pos(x0, bus_y[0], ENTRY_Z) * Box(50, 34, 80)
    render(cut([(base, BODY)], keep) + apart, V / "entry-parts.png", view=(-1.0, 1.1, 0.8), size=(1600, 1000))
    print(f"enclosure: 6 views -> build/{HERE.name}/views/")
