"""Picture of a board's copper coloured by net class, both layers seen from the top.

    tools/kipython tools/classmap.py <board>

Writes build/<board>/plots/classes.svg: the top layer above, the bottom layer below it as seen
through the board, so that a position is the same in both. A layout review of a board with an
isolation gap wants to see which copper belongs to which side; the copper plots of `make plots`
show every track but not its net.

Colours come from boards/<board>/classmap.json if it exists ({"<net class>": "#rrggbb"}); every
other class is grey. Rule areas whose name is listed under "areas" there are hatched.
"""
import json
import os
import sys

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCALE = 12  # pixels per millimetre


def main(name):
    src = os.path.join(REPO, "boards", name)
    board = pcbnew.LoadBoard(os.path.join(src, "eda", name + ".kicad_pcb"))
    cfg = {"classes": {}, "areas": {}}
    if os.path.exists(os.path.join(src, "classmap.json")):
        with open(os.path.join(src, "classmap.json")) as f:
            cfg.update(json.load(f))
    with open(os.path.join(src, "mech.json")) as f:
        m = json.load(f)["board"]
    origin = board.GetDesignSettings().GetAuxOrigin()
    W, H = m["width"], m["height"]
    gap, pad = 6, 3  # between the two layers, around the drawing

    def colour(item):
        return cfg["classes"].get(item.GetNetClassName(), "#9aa3ad") if item.GetNetCode() > 0 else "#9aa3ad"

    def xy(p, dy):
        return (pcbnew.ToMM(p.x - origin.x) + pad) * SCALE, (pcbnew.ToMM(p.y - origin.y) + dy) * SCALE

    def polygons(poly, dy):
        d = []
        for i in range(poly.OutlineCount()):
            rings = [poly.Outline(i)] + [poly.Hole(i, h) for h in range(poly.HoleCount(i))]
            for ring in rings:
                pts = [xy(ring.CPoint(k), dy) for k in range(ring.PointCount())]
                d.append("M" + " L".join("%.1f %.1f" % p for p in pts) + " Z")
        return " ".join(d)

    out = []
    total_h = 2 * H + gap + 2 * pad
    out.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="Helvetica, Arial, sans-serif">' % ((W + 2 * pad) * SCALE, total_h * SCALE))
    out.append('<defs><pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="#444" stroke-width="1.5"/></pattern></defs>')
    out.append('<rect width="100%" height="100%" fill="white"/>')
    for layer, dy, title in ((pcbnew.F_Cu, pad, "Top layer"), (pcbnew.B_Cu, pad + H + gap, "Bottom layer, seen through the board")):
        x0, y0 = pad * SCALE, dy * SCALE
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="%d" fill="#f4f1e8" stroke="#555" stroke-width="2"/>' % (x0, y0, W * SCALE, H * SCALE, m["corner_radius"] * SCALE))
        out.append('<text x="%d" y="%d" font-size="22" fill="#333">%s</text>' % (x0, y0 - 8, title))
        for z in board.Zones():
            if z.GetIsRuleArea() or not z.IsOnLayer(layer):
                continue
            out.append('<path d="%s" fill="%s" fill-opacity="0.45" fill-rule="evenodd"/>' % (polygons(z.GetFilledPolysList(layer), dy), colour(z)))
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                continue
            if t.GetLayer() == layer:
                (ax, ay), (bx, by) = xy(t.GetStart(), dy), xy(t.GetEnd(), dy)
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" stroke-linecap="round"/>' % (ax, ay, bx, by, colour(t), pcbnew.ToMM(t.GetWidth()) * SCALE))
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if not p.IsOnLayer(layer):
                    continue
                bb = p.GetBoundingBox()
                (lx, ly), (hx, hy) = xy(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()), dy), xy(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()), dy)
                hole = p.GetDrillSize().x > 0
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%.1f" fill="%s" stroke="#222" stroke-width="0.8"/>' % (
                    lx, ly, hx - lx, hy - ly, (hx - lx) / 2 if hole else 2, "#ffffff" if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH else colour(p)))
        for t in board.GetTracks():
            if t.GetClass() == "PCB_VIA":
                cx, cy = xy(t.GetPosition(), dy)
                out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="#222" stroke-width="0.8"/><circle cx="%.1f" cy="%.1f" r="%.1f" fill="white"/>' % (
                    cx, cy, pcbnew.ToMM(t.GetWidth(layer)) * SCALE / 2, colour(t), cx, cy, pcbnew.ToMM(t.GetDrill()) * SCALE / 2))
        for z in board.Zones():
            if z.GetIsRuleArea() and z.IsOnLayer(layer) and z.GetZoneName() in cfg["areas"]:
                out.append('<path d="%s" fill="url(#hatch)" fill-opacity="0.5" stroke="#444" stroke-width="1" stroke-dasharray="6 4"/>' % polygons(z.Outline(), dy))
    x = pad * SCALE
    y = (total_h - 1) * SCALE
    for label, c in list(cfg["classes"].items()) + [("other nets", "#9aa3ad")]:
        out.append('<rect x="%d" y="%d" width="22" height="14" fill="%s"/><text x="%d" y="%d" font-size="18" fill="#333">%s</text>' % (x, y - 13, c, x + 28, y, label))
        x += 60 + 11 * len(label)
    for label in cfg["areas"].values():
        out.append('<rect x="%d" y="%d" width="22" height="14" fill="url(#hatch)" stroke="#444"/><text x="%d" y="%d" font-size="18" fill="#333">%s</text>' % (x, y - 13, x + 28, y, label))
        x += 60 + 10 * len(label)
    out.append("</svg>")
    dest = os.path.join(REPO, "build", name, "plots")
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "classes.svg"), "w") as f:
        f.write("\n".join(out))
    print("classmap: build/%s/plots/classes.svg" % name)


if __name__ == "__main__":
    main(sys.argv[1])
