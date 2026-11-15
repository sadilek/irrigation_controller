"""Collision check: populated board (STEP from `make fab`) against every enclosure part.

    uv run python tools/collide.py <board>

Until a board has a layout there is no board STEP. If the enclosure script wrote
build/<board>/envelope.step (the board outline with its connectors as blocks, from mech.json), the
check runs against that and says so.

If the enclosure script wrote build/<board>/plugs.step (the mated plugs as blocks), those are
checked against the enclosure as well.

If it wrote build/<board>/plugs-lid-open.step (plugs that are plugged and pulled with the lid off,
such as a programming plug), those are checked against every enclosure part except the lid, and
against the board itself: such a plug stands among the board's parts.

Reports the overlapping volume per enclosure part and per board solid, and exits 1 if any overlap
exceeds the tolerance. Faces that merely touch (board resting on its standoffs) have zero volume
and pass. It does not check clearances: a part 0.05 mm from a wall passes.
"""
import sys
from pathlib import Path

from build123d import import_step

TOLERANCE_MM3 = 0.01
REPO = Path(__file__).resolve().parents[1]


def overlaps(solids, part):
    """(volume, index, centre) for each solid that overlaps `part` by more than the tolerance."""
    pbb = part.bounding_box()
    hits = []
    for i, solid in enumerate(solids):
        sbb = solid.bounding_box()
        if (sbb.max.X < pbb.min.X or sbb.min.X > pbb.max.X or sbb.max.Y < pbb.min.Y or sbb.min.Y > pbb.max.Y
                or sbb.max.Z < pbb.min.Z or sbb.min.Z > pbb.max.Z):
            continue
        common = solid.intersect(part)
        volume = sum(s.volume for s in common.solids()) if common is not None else 0.0
        if volume > TOLERANCE_MM3:
            hits.append((volume, i, sbb.center()))
    return hits


def report(name, hits, what):
    if not hits:
        print(f"collide: {name}: clear")
        return False
    total = sum(h[0] for h in hits)
    print(f"collide: {name}: COLLISION, {total:.2f} mm3 with {len(hits)} {what}")
    for volume, i, c in sorted(hits, key=lambda h: h[0], reverse=True)[:10]:
        print(f"           solid {i} at ({c.X:.1f}, {c.Y:.1f}, {c.Z:.1f}): {volume:.2f} mm3")
    return True


def main(name: str) -> int:
    build = REPO / "build" / name
    board_step = build / "fab" / f"{name}.step"
    parts = sorted((build / "enclosure").glob("*.step"))
    if not board_step.exists() and (build / "envelope.step").exists():
        board_step = build / "envelope.step"
        print(f"collide: no board STEP yet, checking against the envelope from mech.json ({board_step.relative_to(REPO)})")
    if not board_step.exists() or not parts:
        sys.exit(f"collide: need {board_step.relative_to(REPO)} and build/{name}/enclosure/*.step (run `make fab enclosure`)")

    board = import_step(str(board_step))
    board_solids = board.solids()
    solids = list(board_solids)
    bb = board.bounding_box()
    print(f"collide: board {len(solids)} solids, x {bb.min.X:.1f}..{bb.max.X:.1f}, y {bb.min.Y:.1f}..{bb.max.Y:.1f}, z {bb.min.Z:.1f}..{bb.max.Z:.1f} mm")
    plugs_step = build / "plugs.step"
    if plugs_step.exists():  # mated plugs, written by the enclosure script: not on the board, but in the box
        plugs = import_step(str(plugs_step)).solids()
        solids += list(plugs)
        print(f"collide: plus {len(plugs)} plug solids from {plugs_step.relative_to(REPO)}")
    open_step = build / "plugs-lid-open.step"
    open_plugs = []
    if open_step.exists():
        open_plugs = list(import_step(str(open_step)).solids())
        print(f"collide: plus {len(open_plugs)} solids from {open_step.relative_to(REPO)}, lid off")

    failed = False
    for path in parts:
        part = import_step(str(path))
        hits = overlaps(solids, part)
        if path.stem != "lid":
            hits += [(v, len(solids) + i, c) for v, i, c in overlaps(open_plugs, part)]
        failed |= report(path.stem, hits, "board or plug solid(s)")
    for i, plug in enumerate(open_plugs):
        failed |= report(f"lid-off plug solid {i} against the board", overlaps(board_solids, plug), "board solid(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
