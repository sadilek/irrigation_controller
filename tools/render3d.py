"""Shaded picture of build123d shapes without a CAD program or a graphics card.

    from render3d import render
    render([(shape, (r, g, b)), ...], "view.png", view=(-1, -1.2, 0.9))

`view` points from the model towards the camera. The projection is parallel, so lengths can be
compared across the picture. Each shape is turned into triangles and drawn into a depth buffer
with numpy; edges are darkened where depth or surface direction jumps. It is slow (seconds per
view) and plain, and it needs nothing beyond what build123d already installs.
"""
import numpy as np
from PIL import Image

LIGHT = np.array([-0.35, -0.55, 0.75])
BACKGROUND = (255, 255, 255)


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _triangles(shape, tolerance=0.05, angular_tolerance=0.25):
    """Triangles of a shape as an (n, 3, 3) array, wound so that the normal points out of the solid.

    build123d's own tessellate() stops at a face the mesher left empty; this skips such a face.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    BRepMesh_IncrementalMesh(shape.wrapped, tolerance, False, angular_tolerance, True)
    out = []
    for face in shape.faces():
        location = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(face.wrapped, location)
        if poly is None:
            continue
        trsf = location.Transformation()
        nodes = []
        for i in range(1, poly.NbNodes() + 1):
            p = poly.Node(i).Transformed(trsf)
            nodes.append((p.X(), p.Y(), p.Z()))
        nodes = np.array(nodes)
        index = np.array([poly.Triangle(i).Get() for i in range(1, poly.NbTriangles() + 1)]) - 1
        if face.wrapped.Orientation() == TopAbs_REVERSED:
            index = index[:, ::-1]
        out.append(nodes[index])
    return np.concatenate(out) if out else np.empty((0, 3, 3))


def render(items, path, view=(-1.0, -1.2, 0.9), up=(0, 0, 1), size=(1600, 1000), margin=0.06, supersample=2):
    f = _unit(view)
    r = _unit(np.cross(up, f))
    u = np.cross(f, r)
    light = _unit(LIGHT[0] * r + LIGHT[1] * -u + LIGHT[2] * f + 0.9 * u)

    meshes = []
    for shape, colour in items:
        tris = _triangles(shape)
        if len(tris):
            meshes.append((tris, np.array(colour, dtype=float)))
    if not meshes:
        raise ValueError("render: nothing to draw")

    everything = np.concatenate([m[0].reshape(-1, 3) for m in meshes])
    sx, sy = everything @ r, everything @ u
    w, h = size[0] * supersample, size[1] * supersample
    scale = min(w * (1 - 2 * margin) / (np.ptp(sx) or 1), h * (1 - 2 * margin) / (np.ptp(sy) or 1))
    cx, cy = (sx.max() + sx.min()) / 2, (sy.max() + sy.min()) / 2

    depth = np.full((h, w), -np.inf)
    colour_buf = np.empty((h, w, 3))
    colour_buf[:] = BACKGROUND
    normal_buf = np.zeros((h, w, 3))

    for tris, colour in meshes:
        normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        length = np.linalg.norm(normals, axis=1)
        keep = length > 1e-12
        tris, normals = tris[keep], normals[keep] / length[keep, None]
        facing = normals @ f
        front = facing > 1e-6  # back faces are hidden by the solid they belong to
        tris, normals = tris[front], normals[front]
        px = (tris @ r - cx) * scale + w / 2
        py = h / 2 - (tris @ u - cy) * scale
        pz = tris @ f
        shade = 0.38 + 0.62 * np.clip(normals @ light, 0, 1)
        for i in range(len(tris)):
            x, y, z = px[i], py[i], pz[i]
            x0, x1 = max(int(np.floor(x.min())), 0), min(int(np.ceil(x.max())) + 1, w)
            y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())) + 1, h)
            if x0 >= x1 or y0 >= y1:
                continue
            det = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
            if abs(det) < 1e-12:
                continue
            gx = np.arange(x0, x1) + 0.5
            gy = (np.arange(y0, y1) + 0.5)[:, None]
            a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / det
            b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / det
            c = 1 - a - b
            zz = a * z[0] + b * z[1] + c * z[2]
            window = depth[y0:y1, x0:x1]
            hit = (a >= -1e-9) & (b >= -1e-9) & (c >= -1e-9) & (zz > window)
            if hit.any():
                window[hit] = zz[hit]
                colour_buf[y0:y1, x0:x1][hit] = colour * shade[i]
                normal_buf[y0:y1, x0:x1][hit] = normals[i]

    # Edges: a jump in depth (silhouette, step) or in surface direction (crease).
    solid = np.isfinite(depth)
    d = np.where(solid, depth, depth[solid].min() - 50)
    edge = np.zeros((h, w), dtype=bool)
    for axis in (0, 1):
        jump = np.abs(np.diff(d, axis=axis)) > 0.6
        crease = (np.take(normal_buf, range(1, normal_buf.shape[axis]), axis=axis) * np.take(normal_buf, range(normal_buf.shape[axis] - 1), axis=axis)).sum(axis=2) < 0.8
        both = np.take(solid, range(1, solid.shape[axis]), axis=axis) & np.take(solid, range(solid.shape[axis] - 1), axis=axis)
        mark = jump | (crease & both)
        if axis == 0:
            edge[1:, :] |= mark
            edge[:-1, :] |= mark
        else:
            edge[:, 1:] |= mark
            edge[:, :-1] |= mark
    colour_buf[edge] *= 0.35

    image = Image.fromarray(np.clip(colour_buf, 0, 255).astype(np.uint8))
    image.resize(size, Image.LANCZOS).save(path)
