"""Coarse screw thread for printed parts (build123d), shared by the enclosure models.

    rod = external_thread(major_d, length)            # threaded rod, z = 0 .. length
    nut = internal_thread(major_d, length, outer_d)   # threaded tube, z = 0 .. length

With both at the same position the threads mesh, with `PLAY` between them radially and axially.

A printed thread wants a wide, shallow, rounded profile and generous play; an ISO profile at this
size is all sharp crests. How it is built: the cross-section of a single-start thread, cut square
to the axis, is a circle whose radius rises and falls once per turn. Lofting through copies of
that section, each one turned and lifted a little further, gives the thread as one solid with one
smooth surface. A ridge swept along a helix and fused to a core looks simpler, but OpenCascade
returned invalid solids and wrong volumes for it (build123d 0.13).
"""
import math

from build123d import Align, BuildLine, BuildSketch, Cylinder, Plane, Spline, loft, make_face

PITCH = 2.5
DEPTH = 1.2  # radial height of the ridge
PLAY = 0.3  # gap between rod and nut, radially and on each flank
CREST = 0.5  # width of the flat on top of the ridge
ROOT = 1.5  # width of the ridge at its foot
_MIN = (Align.CENTER, Align.CENTER, Align.MIN)
_POINTS = 24  # points around the section
_STEPS = 8  # sections per turn


def nut_bore_d(major_d: float) -> float:
    """Smallest diameter that clears the rod's ridge."""
    return major_d + 2 * PLAY


def _radius(axial: float, minor_r: float, crest: float, root: float) -> float:
    """Radius of the profile at `axial` (distance from the middle of the ridge, along the axis)."""
    a = abs(axial)
    if a <= crest / 2:
        return minor_r + DEPTH
    if a >= root / 2:
        return minor_r
    return minor_r + DEPTH * (root / 2 - a) / (root / 2 - crest / 2)


def _section(minor_r: float, crest: float, root: float, z: float):
    """The thread's cross-section at height z: the ridge is at angle 360 degrees x z / PITCH.

    Every section starts at angle 0, so the loft joins points of equal angle and does not twist.
    """
    points = []
    for i in range(_POINTS):
        angle = 2 * math.pi * i / _POINTS
        axial = (angle / (2 * math.pi)) * PITCH - z
        axial -= PITCH * round(axial / PITCH)
        r = _radius(axial, minor_r, crest, root)
        points.append((r * math.cos(angle), r * math.sin(angle)))
    with BuildSketch(Plane.XY.offset(z)) as sketch:
        with BuildLine():
            Spline(*points, periodic=True)
        make_face()
    return sketch.sketch


def _screw(minor_r: float, crest: float, root: float, length: float):
    """Thread solid from one turn below 0 to one turn above `length`; the caller cuts it to size."""
    count = int(round((length + 2 * PITCH) / PITCH * _STEPS))
    sections = [_section(minor_r, crest, root, -PITCH + i * PITCH / _STEPS) for i in range(count + 1)]
    return loft(sections)


def external_thread(major_d: float, length: float):
    """Threaded rod, z = 0 .. length."""
    return _screw(major_d / 2 - DEPTH, CREST, ROOT, length) & Cylinder(major_d / 2 + 1, length, align=_MIN)


def internal_thread(major_d: float, length: float, outer_d: float):
    """Threaded tube of outer diameter `outer_d`, z = 0 .. length: a tube minus a rod grown by PLAY."""
    cutter = _screw(major_d / 2 - DEPTH + PLAY, CREST + 2 * PLAY, ROOT + 2 * PLAY, length)
    return Cylinder(outer_d / 2, length, align=_MIN) - cutter
