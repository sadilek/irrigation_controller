"""Scripted arrangement of the KiCad schematic that Zener generates.

`pcb apply` writes a schematic that is electrically complete but unarranged: every symbol sits in a
grid sorted by part type and every pin ends in a net label. This module turns it into a drawing a
person can review: symbols at chosen positions, wires where two pins are next to each other,
labels and power symbols elsewhere, frames and notes around functional blocks.

A board's schematic.py calls these helpers (run by `make arrange`, plain Python, no KiCad needed).
The script owns positions, wires, labels, power symbols, junctions, no-connect marks, frames and
texts: every run rebuilds them from scratch. Symbols, their fields and the netlist come from
`pcb apply` and are never created here. Connectivity is read from eda/default.net, the netlist
Zener writes for the board, so the drawing cannot invent a connection; after arranging,
`make check` compares the schematic against the Zener source and reports every net that differs.

Coordinates are millimetres on the sheet, x right, y down, on KiCad's 1.27 mm grid. Parts are
addressed by their Zener path ("OUT1.R_GATE"), pins as "<path>.<pin number>".
"""
import os
import re
import sys
import uuid

GRID = 1.27
STUB = 2.54
CHAR = 1.13  # width of one character of 1.27 mm text
NAMESPACE = uuid.UUID("6f1d3c0e-7a55-4a0e-9d0b-2f6f1c3b9a10")


class Q(str):
    """A quoted string in an s-expression."""


def parse(text):
    tokens = re.finditer(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+', text)
    stack, cur = [], None
    for m in tokens:
        t = m.group(0)
        if t == "(":
            stack.append(cur)
            cur = []
        elif t == ")":
            done, cur = cur, stack.pop()
            if cur is None:
                return done
            cur.append(done)
        elif t[0] == '"':
            cur.append(Q(t[1:-1]))
        else:
            cur.append(t)
    raise ValueError("unbalanced s-expression")


def dump(node, depth=0):
    if not isinstance(node, list):
        return '"%s"' % node if isinstance(node, Q) else str(node)
    flat = all(not isinstance(c, list) for c in node)
    if flat or node[0] in ("xy", "at", "start", "end", "size", "center", "mid", "stroke", "font", "justify"):
        return "(" + " ".join(dump(c) for c in node) + ")"
    pad = "\t" * (depth + 1)
    if node[0] == "pts":
        return "(pts\n" + pad + " ".join(dump(c) for c in node[1:]) + "\n" + "\t" * depth + ")"
    head = [dump(c) for c in node if not isinstance(c, list)]
    body = [pad + dump(c, depth + 1) for c in node if isinstance(c, list)]
    return "(" + " ".join(head) + "\n" + "\n".join(body) + "\n" + "\t" * depth + ")"


def child(node, name):
    return next((c for c in node if isinstance(c, list) and c and c[0] == name), None)


def children(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def num(v):
    v = round(float(v), 4)
    return "%d" % v if v == int(v) else ("%.4f" % v).rstrip("0")


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def rotate(x, y, deg):
    """Rotate counter-clockwise as seen on the sheet (y down)."""
    for _ in range(int(deg) % 360 // 90):
        x, y = y, -x
    return x, y


class Part:
    def __init__(self, sch, node, path, ref):
        self.sch, self.node, self.path, self.ref = sch, node, path, ref
        self.lib = sch.lib[child(node, "lib_id")[1]]
        self.x = self.y = None
        self.rot, self.mirror = 0, None

    def to_sheet(self, x, y):
        """Symbol coordinates (y up) to sheet coordinates."""
        y = -y
        if self.mirror == "x":
            y = -y
        elif self.mirror == "y":
            x = -x
        x, y = rotate(x, y, self.rot)
        return round(self.x + x, 4), round(self.y + y, 4)

    def direction(self, deg):
        """Unit vector on the sheet for a direction given in symbol coordinates."""
        dx, dy = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[int(deg) % 360]
        x0, y0 = self.to_sheet(0, 0)
        x1, y1 = self.to_sheet(dx, dy)
        return round(x1 - x0), round(y1 - y0)

    def pin(self, number):
        if number not in self.lib["pins"]:
            sys.exit("schlayout: %s has no pin %r (pins: %s)" % (self.path, number, ", ".join(sorted(self.lib["pins"]))))
        x, y, angle = self.lib["pins"][number]
        return self.to_sheet(x, y), self.direction(angle + 180)

    def bbox(self):
        pts = [self.to_sheet(x, y) for x, y in self.lib["body"]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)


class Schematic:
    def __init__(self, board_dir, name, paper="A3"):
        self.name = name
        self.path = os.path.join(board_dir, "eda", name + ".kicad_sch")
        with open(self.path) as f:
            self.tree = parse(f.read())
        self.root_uuid = child(self.tree, "uuid")[1]
        child(self.tree, "paper")[1] = Q(paper)
        self.lib = {s[1]: self._lib_symbol(s) for s in children(child(self.tree, "lib_symbols"), "symbol")}
        self._read_netlist(os.path.join(board_dir, "eda", "default.net"))

        self.parts, self.templates, keep = {}, {}, []
        for node in self.tree:
            kind = node[0] if isinstance(node, list) else None
            if kind == "symbol":
                ref = self._prop(node, "Reference")[2]
                if ref.startswith("#"):
                    self.templates.setdefault(child(node, "lib_id")[1], node)
                    continue
                path = self._prop(node, "Path")[2]
                self.parts[path] = Part(self, node, path, ref)
            elif kind in ("wire", "label", "global_label", "junction", "no_connect", "text", "rectangle", "polyline", "title_block"):
                continue
            keep.append(node)
        self.tree[:] = keep
        missing = set(self.net_of_ref) - {p.ref for p in self.parts.values()}
        if missing:
            sys.exit("schlayout: in the netlist but not in the schematic: %s (run `make apply` first)" % ", ".join(sorted(missing)))

        self.items = []  # generated nodes, appended before sheet_instances
        self.wires = []  # ((x1, y1), (x2, y2))
        self.attached = set()  # (ref, pin) with a wire, label or power symbol placed by the script
        self.anchors = []  # (point, net) of labels and power symbols
        self.power = {}  # net name -> (lib_id, "up" | "down")
        self.count = 0

    # -- reading ---------------------------------------------------------------------------------
    @staticmethod
    def _prop(node, name):
        return next(c for c in children(node, "property") if c[1] == name)

    @staticmethod
    def _lib_symbol(sym):
        pins, body = {}, []
        for unit in children(sym, "symbol"):
            for pin in children(unit, "pin"):
                at = child(pin, "at")
                x, y, angle = float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0
                pins[child(pin, "number")[1]] = (x, y, angle)
                length = float(child(pin, "length")[1])
                dx, dy = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[int(angle) % 360]
                body.append((x + dx * length, y + dy * length))
            for shape in unit:
                if not isinstance(shape, list):
                    continue
                if shape[0] == "rectangle":
                    body += [tuple(map(float, child(shape, k)[1:3])) for k in ("start", "end")]
                elif shape[0] == "polyline":
                    body += [tuple(map(float, p[1:3])) for p in children(child(shape, "pts"), "xy")]
                elif shape[0] == "circle":
                    cx, cy = map(float, child(shape, "center")[1:3])
                    r = float(child(shape, "radius")[1])
                    body += [(cx - r, cy - r), (cx + r, cy + r)]
                elif shape[0] == "arc":
                    body += [tuple(map(float, child(shape, k)[1:3])) for k in ("start", "mid", "end")]
        return {"pins": pins, "body": body or [(0, 0)]}

    def _read_netlist(self, path):
        if not os.path.exists(path):
            sys.exit("schlayout: %s is missing; run `make apply` first" % path)
        with open(path) as f:
            tree = parse(f.read())
        self.net_of = {}  # (ref, pin) -> net name
        self.nodes = {}  # net name -> [(ref, pin)]
        self.net_of_ref = set()
        for net in children(child(tree, "nets"), "net"):
            name = child(net, "name")[1]
            for node in children(net, "node"):
                key = (child(node, "ref")[1], child(node, "pin")[1])
                self.net_of[key] = name
                self.nodes.setdefault(name, []).append(key)
                self.net_of_ref.add(key[0])

    # -- addressing ------------------------------------------------------------------------------
    def part(self, path):
        if path in self.parts:
            return self.parts[path]
        found = [p for k, p in self.parts.items() if k.startswith(path + ".")]
        if len(found) != 1:
            sys.exit("schlayout: %r names %d parts" % (path, len(found)))
        return found[0]

    def _split(self, spec):
        path, number = spec.rsplit(".", 1)
        return self.part(path), number

    def at(self, spec):
        """Sheet position of a pin's connection point."""
        part, number = self._split(spec)
        return part.pin(number)[0]

    def _point(self, where):
        """A pin spec or a point -> (point, pin key or None)."""
        if isinstance(where, str):
            part, number = self._split(where)
            if part.x is None:
                sys.exit("schlayout: %s is used before it is placed" % part.path)
            return part.pin(number)[0], (part.ref, number)
        return (round(where[0], 4), round(where[1], 4)), None

    # -- placing ---------------------------------------------------------------------------------
    def place(self, path, x, y, rot=0, mirror=None, pin=None, ref=None, value=None):
        """Put a part's origin at (x, y); with pin="3", put that pin's connection point there instead.

        ref and value are (dx, dy, justify) offsets from the origin for the two visible fields,
        or False to hide the value. Without them the fields go beside or above the body.
        """
        p = self.part(path)
        p.rot, p.mirror = rot, mirror
        p.x, p.y = x, y
        if pin is not None:
            (px, py), _ = p.pin(pin)
            p.x, p.y = round(2 * x - px, 4), round(2 * y - py, 4)
        p.fields = (ref, value)
        return p

    def _write_part(self, p):
        node = p.node
        node[:] = [c for c in node if not (isinstance(c, list) and c[0] == "mirror")]
        at = child(node, "at")
        at[1:] = [num(p.x), num(p.y), num(p.rot)]
        if p.mirror:
            node.insert(node.index(at) + 1, ["mirror", p.mirror])
        x1, y1, x2, y2 = p.bbox()
        ends = [p.pin(n)[0] for n in p.lib["pins"]]
        two_pin = len(ends) == 2
        if two_pin and ends[0][0] == ends[1][0]:  # vertical: fields to the right
            defaults = ((x2 + 1.0, (y1 + y2) / 2 - 1.1, "left"), (x2 + 1.0, (y1 + y2) / 2 + 1.1, "left"))
        elif two_pin:  # horizontal: fields above
            top = min(y1, ends[0][1] - 1.0)
            defaults = (((x1 + x2) / 2, top - 2.6, "center"), ((x1 + x2) / 2, top - 0.8, "center"))
        else:
            defaults = ((x1, y1 - 2.9, "left"), (x1, y1 - 1.1, "left"))
        for name, given, default in zip(("Reference", "Value"), p.fields, defaults):
            prop = self._prop(node, name)
            hidden = given is False
            fx, fy, justify = default if given in (None, False) else (p.x + given[0], p.y + given[1], given[2] if len(given) > 2 else "left")
            # KiCad turns and mirrors a field's justification with its symbol. Centred text is the
            # same in every orientation, so the anchor is moved by half the text's width instead.
            half = len(prop[2]) * CHAR / 2
            fx += {"left": half, "right": -half, "center": 0}[justify]
            prop[:] = [c for c in prop if not (isinstance(c, list) and c[0] in ("at", "hide", "effects"))]
            # A stored angle of 90 on a part turned by 90 or 270 reads horizontally.
            prop.append(["at", num(fx), num(fy), "90" if p.rot in (90, 270) else "0"])
            if hidden:
                prop.append(["hide", "yes"])
            prop.append(["effects", ["font", ["size", "1.27", "1.27"]]])
        for prop in children(node, "property"):
            if prop[1] not in ("Reference", "Value"):
                child(prop, "at")[1:] = [num(p.x), num(p.y), "0"]

    # -- drawing ---------------------------------------------------------------------------------
    def _uuid(self, kind):
        self.count += 1
        return Q(str(uuid.uuid5(NAMESPACE, "%s/%s/%d" % (self.name, kind, self.count))))

    def _segment(self, a, b):
        if a == b:
            return
        if a[0] != b[0] and a[1] != b[1]:
            sys.exit("schlayout: wire %s-%s is not horizontal or vertical" % (a, b))
        self.wires.append((a, b))
        self.items.append(["wire", ["pts", ["xy", num(a[0]), num(a[1])], ["xy", num(b[0]), num(b[1])]],
                           ["stroke", ["width", "0"], ["type", "default"]], ["uuid", self._uuid("wire")]])

    def wire(self, *route, first="h"):
        """Wire through pins and points. Two consecutive stops that are not aligned are joined by
        an L, horizontal part first (first="h") or vertical part first (first="v")."""
        stops = []
        for where in route:
            point, key = self._point(where)
            if key:
                self.attached.add(key)
            stops.append(point)
        for a, b in zip(stops, stops[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                corner = (b[0], a[1]) if first == "h" else (a[0], b[1])
                self._segment(a, corner)
                self._segment(corner, b)
            else:
                self._segment(a, b)
        return stops[-1]

    def _label_node(self, name, point, direction):
        angle, justify = {(1, 0): (0, "left"), (-1, 0): (180, "right"), (0, -1): (90, "left"), (0, 1): (270, "right")}[direction]
        return ["label", Q(name), ["at", num(point[0]), num(point[1]), str(angle)],
                ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", justify, "bottom"]], ["uuid", self._uuid("label")]]

    def label(self, where, direction=None, net=None, stub=STUB):
        """Net label. At a pin: on a short stub pointing away from the symbol. At a point: on the
        wire that passes there, text running in `direction` ((1, 0) right, (0, -1) up, ...)."""
        point, key = self._point(where)
        if key:
            part, number = self._split(where)
            out = part.pin(number)[1]
            net = self.net_of[key]
            self.attached.add(key)
            end = (round(point[0] + out[0] * stub, 4), round(point[1] + out[1] * stub, 4))
            self._segment(point, end)
            point, direction = end, direction or out
        self.items.append(self._label_node(net, point, direction or (1, 0)))
        self.anchors.append((point, net))

    def power_symbol(self, where, net=None, stub=STUB, rot=None):
        """Power symbol (GND, +5V, ...) at a pin's stub end or at a point on a wire."""
        point, key = self._point(where)
        out = (0, 0)
        if key:
            part, number = self._split(where)
            out = part.pin(number)[1]
            net = self.net_of[key]
            self.attached.add(key)
            end = (round(point[0] + out[0] * stub, 4), round(point[1] + out[1] * stub, 4))
            self._segment(point, end)
            point = end
        lib_id, natural = self.power[net]
        if rot is None:
            # Ground points down and a supply up unless the stub leaves sideways.
            rot = {(0, 0): 0, (0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}[out]
            if natural == "up":
                rot = {(0, 0): 0, (0, -1): 0, (0, 1): 180, (1, 0): 270, (-1, 0): 90}[out]
        template = self.templates[lib_id]
        node = parse(dump(template))
        uid = self._uuid("power")
        ref = Q("#PWR%03d" % sum(1 for i in self.items if i[0] == "symbol"))
        child(node, "at")[1:] = [num(point[0]), num(point[1]), str(rot)]
        child(node, "uuid")[1] = uid
        child(node, "pin")[-1][1] = self._uuid("pin")
        for prop in children(node, "property"):
            child(prop, "at")[1:] = [num(point[0]), num(point[1]), "0"]
            if prop[1] == "Reference":
                prop[2] = ref
            if prop[1] == "Value":
                prop[2] = Q(net)
                dx, dy = rotate(0, 3.81 if natural == "down" else -3.81, rot)
                horizontal = rot in (90, 270)
                child(prop, "at")[1:] = [num(point[0] + (dx * 0.6 if horizontal else 0)), num(point[1] + (dy if not horizontal else 2.2)), "0"]
        child(child(child(node, "instances"), "project"), "path")[2][1] = ref
        self.items.append(node)
        self.anchors.append((point, net))

    def text(self, x, y, string, size=1.5, bold=False):
        font = ["font", ["size", num(size), num(size)]]
        if bold:
            font.append(["bold", "yes"])
        self.items.append(["text", Q(string.replace("\n", "\\n")), ["exclude_from_sim", "no"], ["at", num(x), num(y), "0"],
                           ["effects", font, ["justify", "left", "top"]], ["uuid", self._uuid("text")]])

    def box(self, x1, y1, x2, y2, title=None, note=None):
        """Dashed frame around a functional block, title inside the top-left corner."""
        self.items.append(["rectangle", ["start", num(x1), num(y1)], ["end", num(x2), num(y2)],
                           ["stroke", ["width", "0.15"], ["type", "dash"]], ["fill", ["type", "none"]], ["uuid", self._uuid("box")]])
        if title:
            self.text(x1 + 1.5, y1 + 1.5, title, size=2.0, bold=True)
        if note:
            self.text(x1 + 1.5, y1 + 5.5, note, size=1.27)

    def title(self, title, rev, comments=()):
        block = ["title_block", ["title", Q(title)], ["rev", Q(rev)]]
        block += [["comment", str(i + 1), Q(c)] for i, c in enumerate(comments)]
        self.tree.insert(self.tree.index(child(self.tree, "paper")) + 1, block)

    # -- finishing -------------------------------------------------------------------------------
    def _on_segment(self, p, seg, interior):
        (x1, y1), (x2, y2) = seg
        if x1 == x2 == p[0]:
            lo, hi = sorted((y1, y2))
            return lo < p[1] < hi if interior else lo <= p[1] <= hi
        if y1 == y2 == p[1]:
            lo, hi = sorted((x1, x2))
            return lo < p[0] < hi if interior else lo <= p[0] <= hi
        return False

    def finish(self):
        unplaced = sorted(p.path for p in self.parts.values() if p.x is None)
        if unplaced:
            sys.exit("schlayout: no position for: " + ", ".join(unplaced))
        pin_points, done = {}, set()
        for p in self.parts.values():
            self._write_part(p)
            for number in sorted(p.lib["pins"]):
                key = (p.ref, number)
                point = p.pin(number)[0]
                pin_points[key] = point
                # Two pins of one part at one point (ground pin and exposed pad) share one stub.
                if key in self.attached or (p.ref, point) in done:
                    continue
                done.add((p.ref, point))
                net = self.net_of.get(key)
                if net is None or len(self.nodes[net]) < 2:
                    self.items.append(["no_connect", ["at", num(point[0]), num(point[1])], ["uuid", self._uuid("nc")]])
                elif net in self.power:
                    self.power_symbol("%s.%s" % (p.path, number))
                else:
                    self.label("%s.%s" % (p.path, number))

        # Junction dots where three or more wire ends and pins meet, or a wire ends on another wire.
        ends = {}
        for a, b in self.wires:
            for point in (a, b):
                ends[point] = ends.get(point, 0) + 1
        pins_at = {}
        for point in pin_points.values():
            pins_at[point] = pins_at.get(point, 0) + 1
        for point, n in sorted(ends.items()):
            through = sum(1 for seg in self.wires if self._on_segment(point, seg, interior=True))
            if n + pins_at.get(point, 0) + 2 * through >= 3:
                self.items.append(["junction", ["at", num(point[0]), num(point[1])], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", self._uuid("junction")]])

        self._check(pin_points)
        at = self.tree.index(child(self.tree, "sheet_instances"))
        self.tree[at:at] = self.items
        with open(self.path, "w") as f:
            f.write(dump(self.tree) + "\n")
        print("schlayout: %d parts, %d wires -> %s" % (len(self.parts), len(self.wires), os.path.relpath(self.path)))

    def _check(self, pin_points):
        """Every net must end up as one connected group, and no two nets may touch.

        Things are connected when they share a point with a wire end or lie on a wire; labels and
        power symbols of one name are connected to each other. This repeats in small what KiCad
        does, so a mistake in a board's schematic.py stops here with the net's name."""
        parent = {}

        def find(a):
            parent.setdefault(a, a)
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            parent[find(a)] = find(b)

        points = set(pin_points.values()) | {p for seg in self.wires for p in seg} | {p for p, _ in self.anchors}
        for seg in self.wires:
            for p in points:
                if self._on_segment(p, seg, interior=False):
                    union(p, seg[0])
        for point, net in self.anchors:
            union(point, ("net", net))
        roots, nets_at, problems = {}, {}, []
        for key, point in sorted(pin_points.items()):
            net = self.net_of.get(key)
            if net is None or len(self.nodes[net]) < 2:
                continue
            root = find(point)
            nets_at.setdefault(root, set()).add(net)
            if roots.setdefault(net, root) != root:
                problems.append("net %s: pin %s.%s is not connected to the rest (wire it, or put a label on its wire)" % (net, key[0], key[1]))
        for nets in nets_at.values():
            if len(nets) > 1:
                problems.append("nets joined by the drawing: " + ", ".join(sorted(nets)))
        if problems:
            sys.exit("schlayout: " + "\n            ".join(sorted(set(problems))))

    def pins(self, path):
        """Pin positions of a placed part, for writing a schematic.py."""
        p = self.part(path)
        return {n: p.pin(n) for n in p.lib["pins"]}
