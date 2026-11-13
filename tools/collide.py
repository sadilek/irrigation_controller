"""Collision check: populated board (STEP from `make fab`) against every enclosure part.

    uv run python tools/collide.py <board>

Reports the overlapping volume per enclosure part and per board solid, and exits 1 if any overlap
exceeds the tolerance. Faces that merely touch (board resting on its standoffs) have zero volume
and pass. It does not check clearances: a part 0.05 mm from a wall passes.
"""
import sys
from pathlib import Path

from build123d import import_step

TOLERANCE_MM3 = 0.01
REPO = Path(__file__).resolve().parents[1]


def main(name: str) -> int:
    build = REPO / "build" / name
    board_step = build / "fab" / f"{name}.step"
    parts = sorted((build / "enclosure").glob("*.step"))
    if not board_step.exists() or not parts:
        sys.exit(f"collide: need {board_step.relative_to(REPO)} and build/{name}/enclosure/*.step (run `make fab enclosure`)")

    board = import_step(str(board_step))
    solids = board.solids()
    bb = board.bounding_box()
    print(f"collide: board {len(solids)} solids, x {bb.min.X:.1f}..{bb.max.X:.1f}, y {bb.min.Y:.1f}..{bb.max.Y:.1f}, z {bb.min.Z:.1f}..{bb.max.Z:.1f} mm")

    failed = False
    for path in parts:
        part = import_step(str(path))
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
                c = sbb.center()
                hits.append((volume, i, c))
        if hits:
            failed = True
            total = sum(h[0] for h in hits)
            print(f"collide: {path.stem}: COLLISION, {total:.2f} mm3 with {len(hits)} board solid(s)")
            for volume, i, c in sorted(hits, reverse=True)[:10]:
                print(f"           solid {i} at ({c.X:.1f}, {c.Y:.1f}, {c.Z:.1f}): {volume:.2f} mm3")
        else:
            print(f"collide: {path.stem}: clear")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
