"""A small deterministic router for the part of a board that needs no judgement.

Used through `Layout.router()` in tools/kilayout.py, inside KiCad's Python. It connects the pads
of one net at a time on a 0.1 mm grid, on two layers, with 45 degree bends, shortest path first
(Dijkstra with a price for bends and vias). There is no rip-up: nets are routed in the order the
board's layout.py lists them, and a net that finds no way stops the build with its name.

Why it exists: Freerouting left connections open around a 0.4 mm pitch package and wrote tracks
below the minimum width (docs/toolchain.md, "What does not hold up"). This router is cruder, but
the same input gives the same copper on every run and every failure has a name.

What it knows: one clearance for everything inside its region, pad and track outlines as
rectangles and stadiums, holes, rule areas that forbid tracks, vias kept off pads. What it does
not know: custom rules. A board keeps it away from copper with larger clearances by the region
it hands over. `make drc` is the check on its result, as on every other track.
"""
import heapq
import math
import sys

import pcbnew

UM = 1000  # KiCad's internal unit is the nanometre; the router counts in micrometres
STEP = 100  # grid, micrometres
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
ORTH, DIAG, BEND, VIA_COST = 10, 14, 4, 150


class Router:
    def __init__(self, layout, region, clearance=0.2, via=(0.6, 0.3)):
        self.L = layout
        self.x0, self.y0, x1, y1 = [int(round(v * 1000)) for v in region]
        self.nx = (x1 - self.x0) // STEP + 1
        self.ny = (y1 - self.y0) // STEP + 1
        self.clear = int(round(clearance * 1000))
        self.via_d, self.via_drill = via
        self.layers = (pcbnew.F_Cu, pcbnew.B_Cu)
        # Per layer and grid node: 0 free, n > 0 only net n may put a 0.2 mm track here, -1 nobody.
        self.occ = {l: [0] * (self.nx * self.ny) for l in self.layers}
        self.novia = bytearray(self.nx * self.ny)  # on a pad of any net or layer
        self.tree = {}  # net code -> nodes (layer, i, j) already joined to its first pad
        self.tips = {}  # net code -> node where pre-drawn copper of the net ends (see reserve)
        self.via_wide = (int(self.via_d * 500) - 1) // STEP  # via radius beyond the narrow track's half width, in steps
        self.reach = self.clear + STEP  # clearance plus half of the narrowest track
        b = layout.board
        for fp in b.GetFootprints():
            for pad in fp.Pads():
                self._pad(pad)
        for t in b.GetTracks():
            self._track(t)
        for z in b.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowTracks():
                self._area(z)

    # -- obstacles -------------------------------------------------------------
    def _um(self, v):
        return int(round(pcbnew.ToMM(v) * 1000))

    def _xy(self, p):
        return self._um(p.x) - int(self.L.ox * 1000), self._um(p.y) - int(self.L.oy * 1000)

    def _mark(self, layer, k, net):
        o = self.occ[layer]
        if o[k] == 0:
            o[k] = net
        elif o[k] != net:
            o[k] = -1

    def _rect(self, layers, net, lx, ly, hx, hy, novia=False):
        """Every node strictly inside the rectangle; a node on its edge is exactly at clearance."""
        i0, i1 = max(0, (lx - self.x0) // STEP + 1), min(self.nx - 1, -((self.x0 - hx) // STEP) - 1)
        j0, j1 = max(0, (ly - self.y0) // STEP + 1), min(self.ny - 1, -((self.y0 - hy) // STEP) - 1)
        for j in range(j0, j1 + 1):
            row = j * self.nx
            for i in range(i0, i1 + 1):
                if novia:
                    self.novia[row + i] = 1
                else:
                    for l in layers:
                        self._mark(l, row + i, net)

    def _stadium(self, layers, net, a, b, r):
        """Every node closer than r to the segment a-b."""
        (ax, ay), (bx, by) = a, b
        i0, i1 = max(0, (min(ax, bx) - r - self.x0) // STEP), min(self.nx - 1, (max(ax, bx) + r - self.x0) // STEP + 1)
        j0, j1 = max(0, (min(ay, by) - r - self.y0) // STEP), min(self.ny - 1, (max(ay, by) + r - self.y0) // STEP + 1)
        dx, dy = bx - ax, by - ay
        d2 = dx * dx + dy * dy
        for j in range(j0, j1 + 1):
            y = self.y0 + j * STEP
            for i in range(i0, i1 + 1):
                x = self.x0 + i * STEP
                t = 0.0 if d2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / d2))
                ex, ey = x - ax - t * dx, y - ay - t * dy
                if ex * ex + ey * ey < r * r - 1:
                    for l in layers:
                        self._mark(l, j * self.nx + i, net)

    def _pad(self, pad):
        layers = [l for l in self.layers if pad.IsOnLayer(l)]
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            layers, net = self.layers, -2  # a hole: nobody's
        elif not layers:
            return
        else:
            net = pad.GetNetCode() or -2
        bb = pad.GetBoundingBox()
        ox, oy = int(self.L.ox * 1000), int(self.L.oy * 1000)
        lx, ly, hx, hy = self._um(bb.GetLeft()) - ox, self._um(bb.GetTop()) - oy, self._um(bb.GetRight()) - ox, self._um(bb.GetBottom()) - oy
        r = self.reach + (50 if net == -2 else 0)  # hole clearance is 0.25 mm
        self._rect(layers, net, lx - r, ly - r, hx + r, hy + r)
        v = int(self.via_d * 500) + 50
        self._rect(layers, net, lx - v, ly - v, hx + v, hy + v, novia=True)

    def _track(self, t):
        if t.GetClass() == "PCB_VIA":
            c = self._xy(t.GetPosition())
            self._stadium(self.layers, t.GetNetCode(), c, c, self._um(t.GetWidth(pcbnew.F_Cu)) // 2 + self.reach)
        else:
            self._stadium([t.GetLayer()], t.GetNetCode(), self._xy(t.GetStart()), self._xy(t.GetEnd()), self._um(t.GetWidth()) // 2 + self.reach)

    def _area(self, zone):
        poly = zone.Outline()
        bb = zone.GetBoundingBox()
        ox, oy = int(self.L.ox * 1000), int(self.L.oy * 1000)
        layers = [l for l in self.layers if zone.IsOnLayer(l)]
        r = self.reach
        i0, i1 = max(0, (self._um(bb.GetLeft()) - ox - r - self.x0) // STEP), min(self.nx - 1, (self._um(bb.GetRight()) - ox + r - self.x0) // STEP + 1)
        j0, j1 = max(0, (self._um(bb.GetTop()) - oy - r - self.y0) // STEP), min(self.ny - 1, (self._um(bb.GetBottom()) - oy + r - self.y0) // STEP + 1)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                p = pcbnew.VECTOR2I(pcbnew.FromMM((self.x0 + i * STEP + ox) / 1000.0), pcbnew.FromMM((self.y0 + j * STEP + oy) / 1000.0))
                if poly.Contains(p, -1, pcbnew.FromMM(r / 1000.0)):
                    for l in layers:
                        self._mark(l, j * self.nx + i, -2)

    # -- search ----------------------------------------------------------------
    def _free(self, layer, i, j, net, wide):
        if not (0 <= i < self.nx and 0 <= j < self.ny):
            return False
        o = self.occ[layer]
        if wide == 0:
            v = o[j * self.nx + i]
            return v == 0 or v == net
        for jj in range(max(0, j - wide), min(self.ny, j + wide + 1)):
            for ii in range(max(0, i - wide), min(self.nx, i + wide + 1)):
                v = o[jj * self.nx + ii]
                if v != 0 and v != net:
                    return False
        return True

    def _via_ok(self, i, j, net):
        if self.novia[j * self.nx + i]:
            return False
        wide = (int(self.via_d * 500) - STEP + STEP - 1) // STEP  # via radius beyond the narrow track's half width
        return all(self._free(l, i, j, net, wide) for l in self.layers)

    def _node(self, x, y):
        return (int(round(x * 1000)) - self.x0 + STEP // 2) // STEP, (int(round(y * 1000)) - self.y0 + STEP // 2) // STEP

    def _pos(self, i, j):
        return ((self.x0 + i * STEP) / 1000.0, (self.y0 + j * STEP) / 1000.0)

    def _terminals(self, net, only):
        """(name, exact position, layers) of the net's pads inside the region."""
        out = []
        for ref, fp in sorted(self.L.footprints.items()):
            for pad in fp.Pads():
                if pad.GetNetname() != net:
                    continue
                x, y = self.L.pad(ref, pad.GetNumber())
                i, j = self._node(x, y)
                if not (0 <= i < self.nx and 0 <= j < self.ny):
                    continue
                name = "%s.%s" % (ref, pad.GetNumber())
                if only is not None and name not in only:
                    continue
                out.append((name, (x, y), [l for l in self.layers if pad.IsOnLayer(l)]))
        return out

    def dump(self, x1, y1, x2, y2):
        """Print the obstacle map of a window, one character per grid node, for a net that got stuck."""
        (i1, j1), (i2, j2) = self._node(x1, y1), self._node(x2, y2)
        i1, j1, i2, j2 = max(0, i1), max(0, j1), min(self.nx - 1, i2), min(self.ny - 1, j2)
        for layer in self.layers:
            print("%s, x %.1f..%.1f" % (self.L.board.GetLayerName(layer), self._pos(i1, 0)[0], self._pos(i2, 0)[0]))
            for j in range(j1, j2 + 1):
                row = self.occ[layer][j * self.nx + i1: j * self.nx + i2 + 1]
                print("%6.1f " % self._pos(0, j)[1] + "".join("." if v == 0 else "#" if v < 0 else chr(65 + v % 58) for v in row))

    def reserve(self, net, x, y):
        """Keep room for a via of this net at (x, y): other nets stay out until it is routed."""
        c = (int(round(x * 1000)), int(round(y * 1000)))
        code = self.L.net(net).GetNetCode()
        self._stadium(self.layers, code, c, c, int(self.via_d * 500) + self.reach)
        self.tips[code] = self._node(x, y)

    def _own(self, code):
        """Grid nodes on copper the net already has, and which of them neighbour each other."""
        nodes, vias = set(), set()
        for t in self.L.board.GetTracks():
            if t.GetNetCode() != code:
                continue
            if t.GetClass() == "PCB_VIA":
                x, y = self._xy(t.GetPosition())
                n = ((x - self.x0 + STEP // 2) // STEP, (y - self.y0 + STEP // 2) // STEP)
                vias.add(n)
                nodes |= {(l,) + n for l in self.layers}
            else:
                (ax, ay), (bx, by) = self._xy(t.GetStart()), self._xy(t.GetEnd())
                steps = max(1, int(max(abs(bx - ax), abs(by - ay)) // (STEP // 2)))
                for k in range(steps + 1):
                    x, y = ax + (bx - ax) * k // steps, ay + (by - ay) * k // steps
                    if (x - self.x0) % STEP == 0 and (y - self.y0) % STEP == 0:
                        nodes.add((t.GetLayer(), (x - self.x0) // STEP, (y - self.y0) // STEP))
        return {n for n in nodes if 0 <= n[1] < self.nx and 0 <= n[2] < self.ny}, vias

    def _flood(self, start, own, vias):
        """Everything reachable from `start` along the net's existing copper."""
        seen, queue = set(start), list(start)
        while queue:
            l, i, j = queue.pop()
            near = [(l, i + di, j + dj) for di, dj in DIRS]
            if (i, j) in vias:
                near += [(o, i, j) for o in self.layers if o != l]
            for n in near:
                if n in own and n not in seen:
                    seen.add(n)
                    queue.append(n)
        return seen

    def route(self, net, width=0.2, only=None, via_cost=VIA_COST):
        """Join the net's pads inside the region into one tree, starting from whatever copper the
        net already has at each pad. `only`: pads like "U_MCU.12", to connect a subset."""
        only = None if only is None else {"%s.%s" % (self.L.ref(n.rsplit(".", 1)[0]), n.rsplit(".", 1)[1]) for n in only}
        code = self.L.net(net).GetNetCode()
        wide = max(0, (int(round(width * 500)) - STEP + STEP - 1) // STEP)
        terms = self._terminals(net, only)
        if len(terms) < 2 and code not in self.tree:
            return
        tree = self.tree.setdefault(code, set())
        own, vias = self._own(code)
        self.own_vias = vias
        todo = []
        for name, xy, layers in terms:
            i, j = self._node(*xy)
            nodes = self._flood({(l, i, j) for l in layers}, own, vias)
            tip = self.tips.get(code)
            if tip and (pcbnew.F_Cu,) + tip in nodes:
                nodes = {(pcbnew.F_Cu,) + tip}  # continue from the end of the fan, not from its middle
            if not tree:
                tree |= nodes
                self._stub(net, layers[0], xy, (i, j), width)
            elif not (nodes & tree):
                todo.append((name, xy, layers, nodes))
        while todo:
            targets = {}
            for t in todo:
                for n in t[3]:
                    targets[n] = t
            # Look near the pads first; the whole region only if that fails.
            box = [f(n[k] for n in list(tree) + list(targets)) for k, f in ((1, min), (2, min), (1, max), (2, max))]
            box = (box[0] - 50, box[1] - 50, box[2] + 50, box[3] + 50)
            path = self._search(code, tree, targets, wide, via_cost, box) or self._search(code, tree, targets, wide, via_cost, None)
            if path is None:
                for t in todo:
                    self.dump(t[1][0] - 3, t[1][1] - 3, t[1][0] + 3, t[1][1] + 3)
                sys.exit("layout: router found no way for %s to %s (maps above: '.' free, '#' closed to every net, "
                         "a letter: open to one net only)" % (net, ", ".join(t[0] for t in todo)))
            hit = targets[path[-1]]
            self._emit(net, code, path, width)
            i, j = self._node(*hit[1])
            if any((l, i, j) == path[-1] for l in hit[2]):  # arrived at the pad itself, not at copper leading to it
                self._stub(net, path[-1][0], hit[1], (i, j), width)
            tree |= set(path) | hit[3]
            todo = [t for t in todo if not (t[3] & tree)]

    def _stub(self, net, layer, xy, node, width):
        """From a pad's exact centre to its grid node, when the centre is off the grid."""
        p = self._pos(*node)
        if abs(p[0] - xy[0]) > 1e-6 or abs(p[1] - xy[1]) > 1e-6:
            self.L.track(net, layer, [xy, p], width)

    def _search(self, code, tree, targets, wide, via_cost, box):
        nx, ny = self.nx, self.ny
        # What this net may enter, per layer, as one byte per node.
        ok = {l: bytearray(1 if v == 0 or v == code else 0 for v in self.occ[l]) for l in self.layers}
        memo_wide, memo_via = {l: {} for l in self.layers}, {}

        def free(l, i, j):
            if not (0 <= i < nx and 0 <= j < ny):
                return False
            k = j * nx + i
            if wide == 0:
                return ok[l][k]
            m = memo_wide[l]
            if k not in m:
                m[k] = self._block(ok[l], i, j, wide)
            return m[k]

        def via_ok(i, j):
            k = j * nx + i
            if k not in memo_via:
                memo_via[k] = not self.novia[k] and all(self._block(ok[l], i, j, self.via_wide) for l in self.layers)
            return memo_via[k]

        heap, best, back = [], {}, {}
        for n in sorted(tree):
            s = (n[0], n[1], n[2], 8)
            best[s] = 0
            heapq.heappush(heap, (0, s))
        while heap:
            cost, s = heapq.heappop(heap)
            if cost > best.get(s, 1 << 60):
                continue
            l, i, j, d = s
            if (l, i, j) in targets:
                path = [(l, i, j)]
                while s in back:
                    s = back[s]
                    if path[-1] != s[:3]:
                        path.append(s[:3])
                return path[::-1]
            for nd, (di, dj) in enumerate(DIRS):
                turn = 0 if d == 8 else min((nd - d) % 8, (d - nd) % 8)
                if turn > 2:
                    continue  # no acute bends
                ni, nj = i + di, j + dj
                if box and not (box[0] <= ni <= box[2] and box[1] <= nj <= box[3]):
                    continue
                if not free(l, ni, nj):
                    continue
                if di and dj and not (free(l, ni, j) and free(l, i, nj)):
                    continue
                c = cost + (DIAG if di and dj else ORTH) + turn * BEND
                t = (l, ni, nj, nd)
                if c < best.get(t, 1 << 60):
                    best[t], back[t] = c, s
                    heapq.heappush(heap, (c, t))
            mine = (i, j) in self.own_vias
            if mine or via_ok(i, j):
                other = self.layers[1] if l == self.layers[0] else self.layers[0]
                t, c = (other, i, j, 8), cost + (0 if mine else via_cost)
                if c < best.get(t, 1 << 60):
                    best[t], back[t] = c, s
                    heapq.heappush(heap, (c, t))
        return None

    def _block(self, ok, i, j, r):
        """True if every node within r steps of (i, j) is open."""
        if i < r or j < r or i + r >= self.nx or j + r >= self.ny:
            return False
        nx, w = self.nx, 2 * r + 1
        full = b"\x01" * w
        for jj in range(j - r, j + r + 1):
            k = jj * nx + i - r
            if ok[k:k + w] != full:
                return False
        return True

    def _emit(self, net, code, path, width):
        """Turn a node path into tracks and vias, and make them obstacles for the nets that follow."""
        run = [path[0]]
        for a, b in zip(path, path[1:]):
            if a[0] != b[0]:
                self._run(net, code, run, width)
                if (a[1], a[2]) not in self.own_vias:
                    x, y = self._pos(a[1], a[2])
                    self.L.via(net, x, y, self.via_d, self.via_drill)
                    c = (self.x0 + a[1] * STEP, self.y0 + a[2] * STEP)
                    self._stadium(self.layers, code, c, c, int(self.via_d * 500) + self.reach)
                    self.own_vias.add((a[1], a[2]))
                run = [b]
            else:
                run.append(b)
        self._run(net, code, run, width)

    def _run(self, net, code, run, width):
        if len(run) < 2:
            return
        pts = [run[0]]
        for a, b, c in zip(run, run[1:], run[2:]):
            if (b[1] - a[1], b[2] - a[2]) != (c[1] - b[1], c[2] - b[2]):
                pts.append(b)
        pts.append(run[-1])
        self.L.track(net, run[0][0], [self._pos(p[1], p[2]) for p in pts], width)
        for a, b in zip(pts, pts[1:]):
            self._stadium([run[0][0]], code, (self.x0 + a[1] * STEP, self.y0 + a[2] * STEP), (self.x0 + b[1] * STEP, self.y0 + b[2] * STEP), int(round(width * 500)) + self.reach)

    def stitch(self, net, pads, width=0.4):
        """A short track from each pad to a via: ties a zone's pad to the same net's zone on the other layer."""
        code = self.L.net(net).GetNetCode()
        wide = max(0, (int(round(width * 500)) - STEP + STEP - 1) // STEP)
        for name in pads:
            ref, number = name.rsplit(".", 1)
            xy = self.L.pad(ref, number)
            i, j = self._node(*xy)
            layer = next(l for l in self.layers if any(p.GetNumber() == number and p.IsOnLayer(l) for p in self.L.footprints[self.L.ref(ref)].Pads()))
            seen, queue, back = {(i, j)}, [(i, j)], {}
            hit = None
            while queue and hit is None:
                nxt = []
                for (ci, cj) in queue:
                    if self._via_ok(ci, cj, code):
                        hit = (ci, cj)
                        break
                    for di, dj in DIRS[::2]:
                        n = (ci + di, cj + dj)
                        if n not in seen and self._free(layer, n[0], n[1], code, wide):
                            seen.add(n)
                            back[n] = (ci, cj)
                            nxt.append(n)
                queue = nxt
            if hit is None and width > 0.2:
                self.stitch(net, [name], width=0.2)  # hemmed in: try again with a narrow track
                continue
            if hit is None:
                sys.exit("layout: no room for a %s via at %s" % (net, name))
            path = [hit]
            while path[-1] in back:
                path.append(back[path[-1]])
            path = [(layer, a, b) for a, b in path[::-1]]
            self._stub(net, layer, xy, (i, j), width)
            self._run(net, code, path, width)
            x, y = self._pos(*hit)
            self.L.via(net, x, y, self.via_d, self.via_drill)
            c = (self.x0 + hit[0] * STEP, self.y0 + hit[1] * STEP)
            self._stadium(self.layers, code, c, c, int(self.via_d * 500) + self.reach)
