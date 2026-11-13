"""Scripted board layout on top of KiCad's own Python module (pcbnew).

Run with KiCad's bundled interpreter (tools/kipython), not with the project venv:
pcbnew is only importable there, and it works headless (no KiCad window, no IPC API).

A board's layout.py calls these helpers. The script owns outline, placement, zones and
tracks: every run rebuilds them from scratch, so the committed .kicad_pcb is reproducible
from sources. Footprints and nets come from `pcb apply` (Zener) and are never created here.
"""
import json
import os
import subprocess
import sys

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREEROUTING = os.path.join(REPO, ".tools", "bin", "freerouting")

mm = pcbnew.FromMM


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
        ds = self.board.GetDesignSettings()
        ds.SetAuxOrigin(self.pt(0, 0))
        ds.SetGridOrigin(self.pt(0, 0))

    def pt(self, x, y):
        return pcbnew.VECTOR2I(mm(self.ox + x), mm(self.oy + y))

    # -- reset -----------------------------------------------------------------
    def clear(self):
        """Remove everything this script owns: outline, tracks, vias, zones."""
        b = self.board
        doomed = list(b.GetTracks()) + list(b.Zones())
        doomed += [d for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
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

    def _shape(self):
        s = pcbnew.PCB_SHAPE(self.board)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        self.board.Add(s)
        return s

    def _line(self, x1, y1, x2, y2):
        s = self._shape()
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(self.pt(x1, y1))
        s.SetEnd(self.pt(x2, y2))

    def _arc(self, a, m, e):
        s = self._shape()
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetArcGeometry(self.pt(*a), self.pt(*m), self.pt(*e))

    # -- placement -------------------------------------------------------------
    def place(self, ref, x, y, rot=0.0, side="top"):
        fp = self.footprints.get(ref)
        if fp is None:
            sys.exit("layout: footprint %s is not on the board (run `make apply` first?)" % ref)
        if (side == "bottom") != fp.IsFlipped():
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetPosition(self.pt(x, y))
        fp.SetOrientationDegrees(rot)
        self.placed.add(ref)

    def place_mounting_holes(self):
        for ref, (x, y) in self.mech["mounting_holes"].items():
            self.place(ref, x, y)
            self.footprints[ref].Reference().SetVisible(False)  # no silkscreen label next to a screw head

    def check_all_placed(self):
        missing = sorted(set(self.footprints) - self.placed)
        if missing:
            sys.exit("layout: no position for " + ", ".join(missing))

    # -- copper ----------------------------------------------------------------
    def zone(self, net, layer, inset=0.0):
        m = self.mech["board"]
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer)
        z.SetNet(self.board.FindNet(net))
        z.SetAssignedPriority(0)
        z.SetIsRuleArea(False)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        o = z.Outline()
        o.NewOutline()
        for x, y in ((inset, inset), (m["width"] - inset, inset), (m["width"] - inset, m["height"] - inset), (inset, m["height"] - inset)):
            o.Append(self.pt(x, y))
        self.board.Add(z)
        return z

    def save(self):
        pcbnew.SaveBoard(self.path, self.board)

    def autoroute(self, passes=20, timeout=600):
        """Freerouting round trip: Specctra DSN out, session file in. Zones are filled afterwards by `make drc`."""
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
        self.save()
        tracks = [t for t in self.board.GetTracks()]
        vias = sum(1 for t in tracks if t.GetClass() == "PCB_VIA")
        print("layout: routed %d track segments, %d vias" % (len(tracks) - vias, vias))
