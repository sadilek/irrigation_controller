"""Prove that a board's custom design rules can fail.

    tools/kipython tools/selftest-drc.py <board> <net> <layer> <x1> <y1> <x2> <y2> <expected>

Copies the board with its project and rule files to build/<board>/selftest/, draws one track of
<net> from (x1, y1) to (x2, y2) (board coordinates, millimetres) on the copy, runs KiCad's DRC on
it and expects the report to name the rule <expected>. The committed board is not touched.

A clean DRC report says nothing if the rule file is missing, a net class lost its nets or a
condition never matches. This check fails in all three cases.
"""
import os
import shutil
import subprocess
import sys

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def main(name, net, layer, x1, y1, x2, y2, expected):
    eda = os.path.join(REPO, "boards", name, "eda")
    out = os.path.join(REPO, "build", name, "selftest")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for ext in (".kicad_pcb", ".kicad_pro", ".kicad_dru"):
        if os.path.exists(os.path.join(eda, name + ext)):
            shutil.copy(os.path.join(eda, name + ext), out)
    path = os.path.join(out, name + ".kicad_pcb")
    board = pcbnew.LoadBoard(path)
    origin = board.GetDesignSettings().GetAuxOrigin()
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(origin.x + pcbnew.FromMM(float(x1)), origin.y + pcbnew.FromMM(float(y1))))
    t.SetEnd(pcbnew.VECTOR2I(origin.x + pcbnew.FromMM(float(x2)), origin.y + pcbnew.FromMM(float(y2))))
    t.SetWidth(pcbnew.FromMM(0.2))
    t.SetLayer(board.GetLayerID(layer))
    t.SetNet(board.GetNetsByName()[net])
    board.Add(t)
    pcbnew.SaveBoard(path, board)
    report = os.path.join(out, "drc.rpt")
    r = subprocess.run([KICAD_CLI, "pcb", "drc", "--severity-all", "--exit-code-violations", "-o", report, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    text = open(report).read() if os.path.exists(report) else ""
    if r.returncode != 0 and expected in text:
        print("selftest: %s: a %s track at (%s, %s) is reported by rule '%s', as expected" % (name, net, x1, y1, expected))
        return 0
    print("selftest: %s: a %s track at (%s, %s) was NOT reported by rule '%s' (see %s)" % (name, net, x1, y1, expected, os.path.relpath(report, REPO)))
    return 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
