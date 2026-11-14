"""Enclosure for the valve node: a sealed box that lies in a valve box in the ground.

    uv run python boards/valve-node/enclosure.py [--no-views] [--lid-drop MM]

Parts: base, lid, gasket, and three identical cable entries on one wall (two bus cables, the valve
wires), each with a nut, a pressure washer and a soft insert that seals around the cable. What every dimension is for: docs/valve-node-enclosure.md.

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
    Align, Box, BuildPart, BuildSketch, Circle, Cone, Cylinder, Location, Locations, Mode, Plane, Pos,
    RectangleRounded, Rot, export_step, export_stl, extrude, loft,
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
GAP = mech["clearance_to_enclosure"]  # board edge to the three walls without cable entries
HOLES = [(x, -y) for x, y in mech["mounting_holes"].values()]  # KiCad y down -> model y up
CONNECTORS = {k: v for k, v in mech["connectors"].items() if not k.startswith("_")}

# --- What the owner still has to measure (assumed until then) -----------------------------------
BUS_CABLE_D = 6.0  # outer diameter of the buried bus cable
VALVE_WIRE_D = 2.2  # outer diameter of one valve wire, with insulation
PLUG_BORE_D = 15.5  # smallest round hole a crimped RJ45 plug passes through (11.7 x 8.1 mm body plus latch)

# --- Box ----------------------------------------------------------------------------------------
WALL = 3.0
FLOOR = 3.0
STANDOFF = 5.0  # board bottom above the floor; mech.json allows 3.5 mm of pins below the board
CABLE_SPACE = 14.0  # board's connector edge to the entry wall: the plug stands 9.5 mm out of the jack
RIM_Z = 22.0  # top of the base; set by the cable entries, which have to end below the rim's top
INNER_R = 8.0  # corner radius of the cavity: the gasket follows it and leaves the corners to the lid screws
RIM = 7.0  # width of the rim on top of the base, from the cavity outwards
RIM_R = 3.0  # outer corner radius of rim and lid
RIM_T = 4.0  # thickness of the rim where it stands out beyond the wall, before its 45 degree underside
LID_T = 4.0

# Gasket: a flat printed ring in a groove, compressed by a narrow ridge under the lid. The lid
# stops on the rim, so the compression is set by geometry and not by how hard a screw is turned.
GROOVE_IN = 1.5  # from the cavity wall to the groove
GROOVE_W = 3.0
GROOVE_DEPTH = 2.5
GASKET_W = 2.6
GASKET_H = 2.0
TONGUE_W = 1.2
TONGUE_H = 1.0  # reaches 0.5 mm into the gasket
LIP_H = 5.0  # rib under the lid, inside the cavity: centres the lid and keeps it flat between the screws
LIP_W = 2.0
LIP_PLAY = 0.4

# Lid screws: M3 into heat-set inserts in the four corners, outside the gasket so that no screw
# hole leads inside.
SCREW_GAP = 1.0  # between groove and insert hole
INSERT_HOLE_D = 4.0  # hole for an M3 heat-set insert (4.6 mm outer diameter, 5.7 mm long)
INSERT_HOLE_DEPTH = 7.5
SCREW_CLEAR_D = 3.4
STANDOFF_D = 8.0
STANDOFF_HOLE_DEPTH = 6.5

# --- Cable entry --------------------------------------------------------------------------------
# Measured along the entry's axis from the inside face of the wall, outwards ("s").
ENTRY_Z = T + 7.0  # axis height: middle of the plug opening of the bus jack
THREAD_D = 26.4
NECK_END = WALL + 5.5  # plain neck, so the tightened nut stays clear of the rim
BOSS_END = NECK_END + 11.0  # tip of the threaded part
SEAT_START = BOSS_END - 11.5
SEAT_SLOPE = 0.16  # radius per length: a cone of 9 degrees half angle
SEAT_R_TIP = 9.6  # seat radius at the tip of the boss
INSERT_START = BOSS_END - 10.0  # where the small end of the insert sits when the nut is hand-tight
SQUEEZE = 1.5  # the insert stands this far out of the boss; tightening the nut pushes it in
WASHER_T = 2.0
WASHER_D = 23.6
NUT_D = 33.0
NUT_WALL = 3.0  # end wall
NUT_THREAD = 12.0
SLIT_W = 0.4

x0, x1 = -GAP, W + GAP  # cavity
y0, y1 = -H - CABLE_SPACE, GAP  # the entry wall is the one at y0, facing the board's connector edge
z_floor = -STANDOFF
z_bottom = z_floor - FLOOR
cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
ZMIN = (Align.CENTER, Align.CENTER, Align.MIN)


def slab(grow: float, z_from: float, z_to: float, radius: float = None):
    """The cavity's outline grown by `grow` (negative: shrunk), as a solid between two heights."""
    with BuildPart() as p:
        with BuildSketch(Plane.XY.offset(z_from)):
            with Locations((cx, cy)):
                RectangleRounded(x1 - x0 + 2 * grow, y1 - y0 + 2 * grow, radius if radius else max(INNER_R + grow, 0.2))
        extrude(amount=z_to - z_from)
    return p.part


def ring(grow_in: float, grow_out: float, z_from: float, z_to: float):
    return slab(grow_out, z_from, z_to) - slab(grow_in, z_from - 0.01, z_to + 0.01)


def corners():
    """(x, y, sx, sy) of the cavity's four corners; sx and sy point outwards."""
    return [(x, y, sx, sy) for x, sx in ((x0, -1), (x1, 1)) for y, sy in ((y0, -1), (y1, 1))]


def screw_points():
    """On each corner's diagonal, just outside the gasket groove."""
    reach = (INNER_R + GROOVE_IN + GROOVE_W + SCREW_GAP + INSERT_HOLE_D / 2) / math.sqrt(2) - INNER_R
    return [(x + sx * reach, y + sy * reach) for x, y, sx, sy in corners()]


def pillars(z_from: float, z_to: float):
    """The rim's outline carried down to the floor at the four corners: solid material for the lid screws."""
    size = INNER_R + RIM
    out = None
    for x, y, sx, sy in corners():
        block = Pos(x + sx * (RIM - size / 2), y + sy * (RIM - size / 2), z_from) * Box(size, size, z_to - z_from, align=ZMIN)
        out = block if out is None else out + block
    return slab(RIM, z_from, z_to, RIM_R) & out


def entry_frame(x: float) -> Location:
    """Local frame of a cable entry: origin on the inside face of the entry wall, z pointing outwards."""
    return Location(Plane(origin=(x, y0, ENTRY_Z), x_dir=(1, 0, 0), z_dir=(0, -1, 0)))


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


# --- Entries, all on the wall that faces the board's connector edge ---------------------------------
bus_x = sorted(CONNECTORS[name]["at"][0] for name in ("J_IN", "J_OUT"))
valve_x = sum(CONNECTORS[name]["at"][0] for name in ("OUT1.J", "OUT2.J")) / 2
ENTRIES = [(bus_x[0], "bus"), (bus_x[1], "bus"), (valve_x, "valve-4")]

# --- Base ---------------------------------------------------------------------------------------
base = slab(WALL, z_bottom, RIM_Z)
overhang = RIM - WALL
# The rim stands out beyond the wall. Its underside slopes at 45 degrees, so it prints without support.
z_rim = RIM_Z - RIM_T
with BuildSketch(Plane.XY.offset(z_rim - overhang)) as low:
    with Locations((cx, cy)):
        RectangleRounded(x1 - x0 + 2 * WALL, y1 - y0 + 2 * WALL, INNER_R + WALL)
with BuildSketch(Plane.XY.offset(z_rim)) as high:
    with Locations((cx, cy)):
        RectangleRounded(x1 - x0 + 2 * RIM, y1 - y0 + 2 * RIM, RIM_R)
rim = loft([low.sketch, high.sketch]) + slab(RIM, z_rim, RIM_Z, RIM_R)
base = base + rim + pillars(z_bottom, RIM_Z)
for x, _ in ENTRIES:
    base = base + entry_frame(x) * entry_boss()
base = base - slab(0, z_floor, RIM_Z + 1)
for x, _ in ENTRIES:
    base = base - entry_frame(x) * entry_bore()
base = base - ring(GROOVE_IN, GROOVE_IN + GROOVE_W, RIM_Z - GROOVE_DEPTH, RIM_Z + 1)
for x, y in screw_points():
    base = base - Pos(x, y, RIM_Z - INSERT_HOLE_DEPTH) * Cylinder(INSERT_HOLE_D / 2, INSERT_HOLE_DEPTH + 1, align=ZMIN)
for x, y in HOLES:
    base = base + Pos(x, y, z_floor) * Cylinder(STANDOFF_D / 2, STANDOFF, align=ZMIN)
for x, y in HOLES:
    base = base - Pos(x, y, -STANDOFF_HOLE_DEPTH) * Cylinder(INSERT_HOLE_D / 2, STANDOFF_HOLE_DEPTH + 1, align=ZMIN)

# --- Lid ----------------------------------------------------------------------------------------
lid_z = RIM_Z - args.lid_drop
lid = slab(RIM, lid_z, lid_z + LID_T, RIM_R)
tongue_in = GROOVE_IN + (GROOVE_W - TONGUE_W) / 2
lid = lid + ring(tongue_in, tongue_in + TONGUE_W, lid_z - TONGUE_H, lid_z + 0.01)
lid = lid + ring(-LIP_PLAY - LIP_W, -LIP_PLAY, lid_z - LIP_H, lid_z + 0.01)
for x, y in screw_points():
    lid = lid - Pos(x, y, lid_z - 1) * Cylinder(SCREW_CLEAR_D / 2, LID_T + 2, align=ZMIN)

gasket_in = GROOVE_IN + (GROOVE_W - GASKET_W) / 2
gasket = ring(gasket_in, gasket_in + GASKET_W, RIM_Z - GROOVE_DEPTH, RIM_Z - GROOVE_DEPTH + GASKET_H)

# --- Entry parts in place ---------------------------------------------------------------------------
one_nut = nut()
nuts = [entry_frame(x) * one_nut for x, _ in ENTRIES]
washers = [entry_frame(x) * washer(p) for x, p in ENTRIES]
inserts = [entry_frame(x) * insert(p) for x, p in ENTRIES]


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
    if sub != "views":
        for stale in (BUILD / sub).iterdir():  # a renamed or dropped part must not stay behind for the collision check
            stale.unlink()

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
    "nut-3x": flip * one_nut,  # end wall on the bed, thread axis upright
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
with_nuts = (base + compound(nuts)).bounding_box()
print(f"enclosure: outside {with_nuts.size.X:.0f} x {with_nuts.size.Y:.0f} x {outer.size.Z + LID_T:.0f} mm over the nuts, "
      f"{outer.size.X:.0f} x {y1 - y0 + 2 * RIM:.0f} mm without them; inside {x1 - x0:.0f} x {y1 - y0:.0f} x {RIM_Z - z_floor:.0f} mm")

# --- Views ----------------------------------------------------------------------------------------
if not args.no_views and not args.lid_drop:
    from render3d import render  # noqa: E402

    BODY, LID, SOFT, NUT, WASHER = (92, 98, 108), (150, 158, 170), (236, 120, 40), (60, 64, 72), (205, 210, 216)
    PCB, PART, CABLE = (40, 130, 70), (40, 40, 44), (120, 150, 190)
    board_items = [(board_plate.part, PCB)] + [(b, PART) for b, _ in blocks]
    entry_items = [(n, NUT) for n in nuts] + [(w, WASHER) for w in washers] + [(i, SOFT) for i in inserts]
    plug_out = 9.5  # how far the plug stands out of the jack
    cables = [entry_frame(x) * Pos(0, 0, -(CABLE_SPACE - plug_out)) * Cylinder(BUS_CABLE_D / 2, 70, align=ZMIN) for x, p in ENTRIES if p == "bus"]
    plugs = [Pos(x - 5.85, -H - plug_out, ENTRY_Z - 4) * Box(11.7, plug_out, 8.1, align=Align.MIN) for x, p in ENTRIES if p == "bus"]
    wires = [entry_frame(valve_x) * Pos(u, v, -6) * Cylinder(VALVE_WIRE_D / 2, 76, align=ZMIN) for u, v in PATTERNS["valve-4"][1]]
    cable_items = [(c, CABLE) for c in cables] + [(p, (225, 225, 225)) for p in plugs] + [(w, (200, 60, 50)) for w in wires]

    def cut(items, keep):
        out = []
        for shape, colour in items:
            part = shape & keep
            if part is not None and part.volume > 1e-6:
                out.append((part, colour))
        return out

    V = BUILD / "views"
    inside = [(base, BODY), (gasket, SOFT)] + entry_items + board_items + cable_items
    render([(base, BODY), (lid, LID)] + entry_items + cable_items, V / "closed.png", view=(-0.7, -1.3, 0.9))
    render(inside, V / "open.png", view=(-0.6, -1.0, 1.4))
    render(inside, V / "top.png", view=(0, 0, 1), up=(0, 1, 0))

    # Section along a bus cable: everything on the far side of the plane through the entry axis.
    x_cut = bus_x[0]
    everything = [(base, BODY), (lid, LID), (gasket, SOFT)] + entry_items + board_items + cable_items
    render(cut(everything, Pos(x_cut + 100, cy, 0) * Box(200, 400, 200)), V / "section.png", view=(-1, 0, 0), size=(1600, 640))
    near = Pos(x_cut + 100, y0 - 5, ENTRY_Z) * Box(200, 62, 60)
    render(cut(everything, near), V / "section-entry.png", view=(-1, 0, 0), size=(1600, 1100))

    # One bus entry taken apart, seen from outside. The washer is turned so that its slot shows.
    frame = entry_frame(bus_x[0])
    apart = [
        (frame * Pos(0, 0, 12) * insert("bus"), SOFT), (frame * Pos(0, 0, 24) * Rot(0, 0, 150) * washer("bus"), WASHER),
        (frame * Pos(0, 0, 46) * one_nut, NUT),
        (frame * Pos(0, 0, -4) * Cylinder(BUS_CABLE_D / 2, 100, align=ZMIN), CABLE),
    ]
    keep = Pos(bus_x[0] - 3, y0, ENTRY_Z) * Box(40, 50, 80)
    render(cut([(base, BODY)], keep) + apart, V / "entry-parts.png", view=(-1.1, -1.0, 0.8), size=(1600, 1000))
    print(f"enclosure: 6 views -> build/{HERE.name}/views/")
