"""Scripted board layout on top of KiCad's own Python module (pcbnew).

Run with KiCad's bundled interpreter (tools/kipython), not with the project venv:
pcbnew is only importable there, and it works headless (no KiCad window, no IPC API).

A board's layout.py calls these helpers. The script owns outline, placement, zones, rule
areas, silkscreen texts and tracks: every run rebuilds them from scratch, so the committed
.kicad_pcb is reproducible from sources. Footprints and nets come from `pcb apply` (Zener) and
are never created here.

Coordinates are millimetres from the board's top-left corner, x right, y down, as in mech.json.

Two kinds of copper:
  * tracks and vias drawn by the script (`track`, `via`): locked, kept as they are;
  * everything else, routed by Freerouting (`autoroute`) around them.
Net classes and custom design rules live in the KiCad project (`write_rules`), so that
`kicad-cli pcb drc` checks them without this script.
"""
import json
import math
import os
import subprocess
import sys

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREEROUTING = os.path.join(REPO, ".tools", "bin", "freerouting")

mm = pcbnew.FromMM
LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu, "F.SilkS": pcbnew.F_SilkS, "B.SilkS": pcbnew.B_SilkS}


def write_rules(board_dir, name, classes, patterns, rules):
    """Net classes, their net-name patterns and custom design rules, written into the KiCad project.

    classes   {"AC": {"clearance": 0.5, "track_width": 0.8, "via_diameter": 0.8, "via_drill": 0.4}, ...}
              on top of the Default class, which Zener writes from the board configuration
              (lib/jlcpcb.zen) on every `make apply` and which therefore cannot be changed here
    patterns  [("AC_*", "AC"), ...]  KiCad net-name patterns, first match wins
    rules     text of <name>.kicad_dru (KiCad custom rules)

    Call it before Layout(): pcbnew reads the project file when it loads the board.
    """
    pro = os.path.join(board_dir, "eda", name + ".kicad_pro")
    with open(pro) as f:
        project = json.load(f)
    net = project["net_settings"]
    default = next(c for c in net["classes"] if c["name"] == "Default")
    net["classes"] = [default]
    for priority, (cname, values) in enumerate(classes.items()):
        c = dict(default, name=cname, priority=priority)
        c.update(values)
        net["classes"].append(c)
    net["netclass_patterns"] = [{"netclass": c, "pattern": p} for p, c in patterns]
    with open(pro, "w") as f:
        json.dump(project, f, indent=2)
        f.write("\n")
    with open(os.path.join(board_dir, "eda", name + ".kicad_dru"), "w") as f:
        f.write(rules.strip() + "\n")


class Layout:
    def __init__(self, board_dir, name, origin=(100.0, 100.0)):
        self.dir = board_dir
        self.name = name
        self.path = os.path.join(board_dir, "eda", name + ".kicad_pcb")
        self.build = os.path.join(REPO, "build", name)
        os.makedirs(self.build, exist_ok=True)
        self.board = pcbnew.LoadBoard(self.path)
        self.ox, self.oy = origin
        with open(os.path.join(board_dir, "mech.json")) as f:
            self.mech = json.load(f)
        self.placed = set()
        # FindFootprintByReference() returns an untyped SWIG pointer in KiCad 10; index the typed list instead.
        self.footprints = {f.GetReference(): f for f in self.board.GetFootprints()}
        # Zener renumbers reference designators when parts are added; its path (`OUT1.R_GATE`) is stable.
        self.refs = {}
        for ref, f in self.footprints.items():
            if f.HasField("Path"):
                path = f.GetFieldText("Path")
                self.refs[path] = ref
                self.refs[path.rsplit(".", 1)[0]] = ref  # generics add a level: `C_MCU.C` is also `C_MCU`
        self.nets = self.board.GetNetsByName()
        self.manual = []  # tracks and vias drawn by the script
        ds = self.board.GetDesignSettings()
        ds.SetAuxOrigin(self.pt(0, 0))
        ds.SetGridOrigin(self.pt(0, 0))

    def pt(self, x, y):
        return pcbnew.VECTOR2I(mm(self.ox + x), mm(self.oy + y))

    # -- reset -----------------------------------------------------------------
    def clear(self):
        """Remove everything this script owns: outline, tracks, vias, zones, rule areas, board texts."""
        b = self.board
        doomed = list(b.GetTracks()) + list(b.Zones())
        doomed += [d for d in b.GetDrawings() if d.GetLayer() in (pcbnew.Edge_Cuts, pcbnew.Cmts_User) or d.GetClass() == "PCB_TEXT"]
        for item in doomed:
            b.Remove(item)
        # KiCad 10.0.1: once Python frees an item removed from the board, pcbnew hands out untyped
        # SwigPyObject pointers for the rest of the process. Keep the removed items alive instead.
        self._graveyard = doomed

    # -- outline ---------------------------------------------------------------
    def outline_from_mech(self):
        m = self.mech["board"]
        w, h, r = m["width"], m["height"], m["corner_radius"]
        self._line(r, 0, w - r, 0)
        self._line(w, r, w, h - r)
        self._line(w - r, h, r, h)
        self._line(0, h - r, 0, r)
        # arcs: start, mid, end (clockwise in KiCad's y-down frame)
        k = r * (1 - 0.7071067811865476)
        self._arc((w - r, 0), (w - k, k), (w, r))
        self._arc((w, h - r), (w - k, h - k), (w - r, h))
        self._arc((r, h), (k, h - k), (0, h - r))
        self._arc((0, r), (k, k), (r, 0))

    def _shape(self, layer=pcbnew.Edge_Cuts):
        s = pcbnew.PCB_SHAPE(self.board)
        s.SetLayer(layer)
        s.SetWidth(mm(0.1))
        self.board.Add(s)
        return s

    def ruler(self, x, y, length=50.0):
        """A line of known length on the comment layer, beside the board: the 1:1 print for a test
        fit (`make plots`) is only worth something if the printer did not scale it."""
        self._line(x, y, x + length, y, pcbnew.Cmts_User)
        for end in (x, x + length):
            self._line(end, y - 1.5, end, y + 1.5, pcbnew.Cmts_User)
        self.text("%g mm: measure this line after printing" % length, x + length / 2, y + 2.5, 1.5, layer=pcbnew.Cmts_User)

    def _line(self, x1, y1, x2, y2, layer=pcbnew.Edge_Cuts):
        s = self._shape(layer)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(self.pt(x1, y1))
        s.SetEnd(self.pt(x2, y2))

    def _arc(self, a, m, e):
        s = self._shape()
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(self.pt(*a), self.pt(*m), self.pt(*e))

    # -- placement -------------------------------------------------------------
    def ref(self, name):
        """Reference designator for a reference or a Zener path."""
        if name in self.footprints:
            return name
        if name in self.refs:
            return self.refs[name]
        sys.exit("layout: footprint %s is not on the board (run `make apply` first?)" % name)

    def place(self, name, x, y, rot=0.0, side="top", label=None):
        """`label`: (dx, dy) of the reference text from the part's origin, or False to hide it."""
        ref = self.ref(name)
        fp = self.footprints[ref]
        if (side == "bottom") != fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(self.pt(x, y))
        fp.SetOrientationDegrees(rot)
        self.placed.add(ref)
        if label is False:
            fp.Reference().SetVisible(False)
        elif label is not None:
            t = fp.Reference()
            t.SetVisible(True)
            t.SetPosition(self.pt(x + label[0], y + label[1]))
            t.SetTextAngleDegrees(0)
            t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            t.SetTextThickness(mm(0.12))

    def place_connectors(self):
        """Connectors whose position the enclosure fixes: mech.json `connectors`, keyed by Zener path."""
        for name, c in self.mech.get("connectors", {}).items():
            if not name.startswith("_"):
                self.place(name, c["at"][0], c["at"][1], rot=c["rotation"], label=False)

    def pad(self, name, number):
        """Position of a pad in board coordinates."""
        for p in self.footprints[self.ref(name)].Pads():
            if p.GetNumber() == str(number):
                pos = p.GetPosition()
                return (round(pcbnew.ToMM(pos.x) - self.ox, 4), round(pcbnew.ToMM(pos.y) - self.oy, 4))
        sys.exit("layout: %s has no pad %s" % (name, number))

    def place_mounting_holes(self):
        for ref, (x, y) in self.mech["mounting_holes"].items():
            self.place(ref, x, y, label=False)  # no silkscreen label next to a screw head

    def check_all_placed(self):
        missing = sorted(set(self.footprints) - self.placed)
        if missing:
            sys.exit("layout: no position for " + ", ".join(missing))

    # -- copper ----------------------------------------------------------------
    def net(self, name):
        if name not in self.nets:
            sys.exit("layout: no net %s" % name)
        return self.nets[name]

    def zone(self, net, layer, inset=0.0, outline=None, solid=False, priority=0):
        """Copper zone. Without `outline` it covers the board; `solid` joins pads without thermal spokes."""
        m = self.mech["board"]
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer)
        z.SetNet(self.net(net))
        z.SetAssignedPriority(priority)
        z.SetIsRuleArea(False)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for x, y in outline or ((inset, inset), (m["width"] - inset, inset), (m["width"] - inset, m["height"] - inset), (inset, m["height"] - inset)):
            o.Append(self.pt(x, y))
        self.board.Add(z)
        return z

    def rule_area(self, name, layers, outline, tracks=True, vias=True, pours=True):
        """Named rule area. `tracks`, `vias`, `pours`: what it forbids. With all three False it only
        gives custom rules a place to refer to (`A.intersectsArea('name')`)."""
        z = pcbnew.ZONE(self.board)
        z.SetIsRuleArea(True)
        z.SetZoneName(name)
        ls = pcbnew.LSET()
        for layer in layers:
            ls.AddLayer(layer)
        z.SetLayerSet(ls)
        z.SetDoNotAllowTracks(tracks)
        z.SetDoNotAllowVias(vias)
        z.SetDoNotAllowZoneFills(pours)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        o = z.Outline()
        o.NewOutline()
        for x, y in outline:
            o.Append(self.pt(x, y))
        self.board.Add(z)
        return z

    def solid(self, name, number):
        """Join this pad to its zone without thermal spokes (a pad hemmed in on three sides gets only one)."""
        for p in self.footprints[self.ref(name)].Pads():
            if p.GetNumber() == str(number):
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

    def fanout(self, name, pitch=0.8, length=2.05, width=0.2, skip=()):
        """Lead the pins of a four-sided fine-pitch package outwards to twice their pitch.

        Each pin leaves straight, the outer ones bend outwards at 45 degrees (the outermost first,
        so the bends stay parallel at full clearance) and all end `length` from the pad row,
        `pitch` apart: far enough for a via beside a neighbour's track. Returns [(net, (x, y))],
        the ends, for the router to continue from. `skip`: pad numbers that get no track but
        keep their place in the fan.
        """
        fp = self.footprints[self.ref(name)]
        c = fp.GetPosition()
        cx, cy = pcbnew.ToMM(c.x) - self.ox, pcbnew.ToMM(c.y) - self.oy
        sides = {}
        for p in fp.Pads():
            if not p.GetNumber() or not p.IsOnLayer(pcbnew.F_Cu):
                continue
            x, y = self.pad(name, p.GetNumber())
            dx, dy = x - cx, y - cy
            if max(abs(dx), abs(dy)) < 0.5:
                continue  # exposed pad
            side = (int(math.copysign(1, dx)), 0) if abs(dx) > abs(dy) else (0, int(math.copysign(1, dy)))
            sides.setdefault(side, []).append((dy if side[0] else dx, x, y, p))
        ends = []
        for (ux, uy), pads in sorted(sides.items()):
            pads.sort(key=lambda t: t[0])
            lateral = [t[0] for t in pads]
            native = min(b - a for a, b in zip(lateral, lateral[1:]))
            mid = (lateral[0] + lateral[-1]) / 2
            for lat, x, y, p in pads:
                if p.GetNumber() in skip or not p.GetNetname() or p.GetNetname().startswith("unconnected"):
                    continue
                k = round((lat - mid) / native)
                shift = abs(k) * (pitch - native)  # sideways, outwards from the middle of the row
                sign = (k > 0) - (k < 0)
                bend = length - 0.6 - 0.2 * abs(k)  # where the 45 degree part starts
                tx, ty = (0, sign) if ux else (sign, 0)
                pts = [(x, y), (x + ux * bend, y + uy * bend),
                       (x + ux * (bend + shift) + tx * shift, y + uy * (bend + shift) + ty * shift),
                       (x + ux * length + tx * shift, y + uy * length + ty * shift)]
                pts = [(round(a, 4), round(b, 4)) for a, b in pts]
                self.track(p.GetNetname(), pcbnew.F_Cu, [q for i, q in enumerate(pts) if i == 0 or q != pts[i - 1]], width)
                ends.append((p.GetNetname(), pts[-1]))
        return ends

    def router(self, region, **options):
        """Grid router for what is left after the scripted tracks (tools/gridroute.py). `region`:
        (x1, y1, x2, y2), the only place it may put copper. Create it after the last `track()`
        call of your own: it reads the board's copper once."""
        from gridroute import Router
        return Router(self, region, **options)

    def keepouts_from_mech(self, sides=24):
        """mech.json `keepouts`: no copper under screw heads (top) and on standoffs (bottom).

        The areas are named `keepout-top` and `keepout-bottom`. They keep zones out by themselves;
        for tracks and vias the board's custom rules need a `disallow` rule that names them
        (KiCad 10.0.1 did not report a track inside a rule area on its own)."""
        for k in self.mech.get("keepouts", []):
            if k["shape"] != "circle":
                sys.exit("layout: keep-out shape %s is not implemented" % k["shape"])
            (x, y), r = k["at"], k["diameter"] / 2
            ring = [(x + r * math.cos(2 * math.pi * i / sides), y + r * math.sin(2 * math.pi * i / sides)) for i in range(sides)]
            self.rule_area("keepout-" + k["side"], [pcbnew.F_Cu if k["side"] == "top" else pcbnew.B_Cu], ring)

    def track(self, net, layer, points, width):
        """A locked polyline. Freerouting routes around it and leaves it alone."""
        n = self.net(net)
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(self.pt(x1, y1))
            t.SetEnd(self.pt(x2, y2))
            t.SetWidth(mm(width))
            t.SetLayer(layer)
            t.SetNet(n)
            t.SetLocked(True)
            self.board.Add(t)
            self.manual.append(t)

    def via(self, net, x, y, diameter=0.6, drill=0.3):
        v = pcbnew.PCB_VIA(self.board)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetPosition(self.pt(x, y))
        v.SetWidth(pcbnew.F_Cu, mm(diameter))
        v.SetDrill(mm(drill))
        v.SetNet(self.net(net))
        v.SetLocked(True)
        self.board.Add(v)
        self.manual.append(v)

    def text(self, s, x, y, size=1.0, layer=pcbnew.F_SilkS, angle=0.0, align="center"):
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(s)
        t.SetLayer(layer)
        t.SetPosition(self.pt(x, y))
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(max(0.12, size * 0.15)))
        t.SetTextAngleDegrees(angle)
        t.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT, "center": pcbnew.GR_TEXT_H_ALIGN_CENTER, "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[align])
        if layer in (pcbnew.B_SilkS, pcbnew.B_Cu):
            t.SetMirrored(True)
        self.board.Add(t)
        return t

    def save(self):
        pcbnew.SaveBoard(self.path, self.board)

    def autoroute(self, passes=20, timeout=600, fence=()):
        """Freerouting round trip: Specctra DSN out, session file in. Zones are filled afterwards by `make drc`.

        `fence`: outlines Freerouting must stay out of on every layer, on top of the board's own
        rule areas. They exist only in the file Freerouting reads. It knows clearances per net
        class but nothing about custom rules, so a board keeps it away from copper it must not
        come near by fencing it in.

        Tracks and vias drawn by the script are exported as fixed wiring and are put back exactly
        as drawn afterwards, whatever the session file says about them.
        """
        fences = [self.rule_area("fence", [pcbnew.F_Cu, pcbnew.B_Cu], outline) for outline in fence]
        self.save()
        dsn = os.path.join(self.build, self.name + ".dsn")
        ses = os.path.join(self.build, self.name + ".ses")
        for p in (dsn, ses):
            if os.path.exists(p):
                os.remove(p)
        if not pcbnew.ExportSpecctraDSN(self.board, dsn):
            sys.exit("layout: Specctra DSN export failed")
        log = os.path.join(self.build, "freerouting.log")
        with open(log, "w") as f:
            r = subprocess.run([FREEROUTING, "-de", dsn, "-do", ses, "--router.autorouter.max_passes", str(passes)], timeout=timeout, stdout=f, stderr=subprocess.STDOUT)
        if r.returncode != 0 or not os.path.exists(ses):
            sys.exit("layout: Freerouting failed, see " + log)
        if not pcbnew.ImportSpecctraSES(self.board, ses):
            sys.exit("layout: Specctra session import failed")
        for z in fences:
            self.board.Remove(z)
        self._graveyard += fences
        self._restore_manual()
        self.save()
        tracks = [t for t in self.board.GetTracks()]
        vias = sum(1 for t in tracks if t.GetClass() == "PCB_VIA")
        print("layout: %d track segments and %d vias, of which %d segments and %d vias drawn by the script" % (
            len(tracks) - vias, vias, sum(1 for t in self.manual if t.GetClass() != "PCB_VIA"), sum(1 for t in self.manual if t.GetClass() == "PCB_VIA")))

    @staticmethod
    def _key(t):
        if t.GetClass() == "PCB_VIA":
            return ("via", t.GetNetCode(), t.GetPosition().x, t.GetPosition().y)
        a, b = (t.GetStart().x, t.GetStart().y), (t.GetEnd().x, t.GetEnd().y)
        return ("track", t.GetNetCode(), t.GetLayer()) + (min(a, b) + max(a, b))

    def _restore_manual(self):
        """After the session import: exactly one copy of every scripted track and via, locked."""
        wanted = {self._key(t): t for t in self.manual}
        present = set()
        for t in list(self.board.GetTracks()):
            k = self._key(t)
            if k in wanted and k not in present:
                present.add(k)
                t.SetLocked(True)
            elif k in wanted:
                self.board.Remove(t)
                self._graveyard.append(t)
        missing = [k for k in wanted if k not in present]
        if missing:
            sys.exit("layout: %d scripted tracks or vias did not survive the Freerouting round trip, e.g. %s" % (len(missing), missing[0]))
