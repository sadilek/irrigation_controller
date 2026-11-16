"""Fabrication data for JLCPCB: Gerbers and drill files (zip), BOM, placement file, STEP.

    tools/kipython tools/fab.py <board>

BOM and placement come from the footprints on the board, because that is where Zener writes the
manufacturer part numbers (the generated schematic does not carry them). Each part number is mapped
to an LCSC number through lib/jlcpcb-parts.csv; an unmapped populated part is an error.
"""
import csv
import os
import shutil
import subprocess
import sys
import zipfile

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KICAD_CLI = os.environ.get("KICAD_CLI", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")


def cli(*args):
    r = subprocess.run([KICAD_CLI] + list(args), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if r.returncode != 0:
        sys.exit("fab: kicad-cli %s failed:\n%s" % (" ".join(args[:3]), r.stdout))


def field(fp, name):
    return fp.GetFieldText(name) if fp.HasField(name) else ""


def centre(fp):
    """The point the placement file gives for a part.

    JLCPCB places its own footprint of the part by this point, and its footprints have their origin
    in the middle of the part. A footprint fetched from LCSC (library lib/lcsc) is that footprint,
    so its origin is used as it is. KiCad's footprints mostly have it there too, but not all: a pin
    header has it on pin 1, a DPAK and a SOT-89 off the middle of their pads. For those the middle
    of the pads' bounding box is used, which is the origin wherever KiCad already has it there.
    """
    if "lcsc" in fp.GetFPID().GetLibNickname().wx_str():
        return fp.GetPosition()
    boxes = [p.GetBoundingBox() for p in fp.Pads()]
    if not boxes:
        return fp.GetPosition()
    return pcbnew.VECTOR2I(int((min(b.GetLeft() for b in boxes) + max(b.GetRight() for b in boxes)) / 2),
                           int((min(b.GetTop() for b in boxes) + max(b.GetBottom() for b in boxes)) / 2))


def main(name):
    pcb = os.path.join(REPO, "boards", name, "eda", name + ".kicad_pcb")
    out = os.path.join(REPO, "build", name, "fab")
    shutil.rmtree(out, ignore_errors=True)
    gerbers = os.path.join(out, "gerbers")
    os.makedirs(gerbers)

    with open(os.path.join(REPO, "lib", "jlcpcb-parts.csv"), newline="") as f:
        parts = {row["mpn"]: row for row in csv.DictReader(f)}

    board = pcbnew.LoadBoard(pcb)
    origin = board.GetDesignSettings().GetAuxOrigin()
    bom, cpl, problems, skipped = {}, [], [], []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if fp.IsExcludedFromBOM() or fp.IsDNP():
            skipped.append(ref)
            continue
        mpn = field(fp, "Mpn")
        part = parts.get(mpn)
        if not mpn or part is None:
            problems.append("%s: part number %r has no row in lib/jlcpcb-parts.csv" % (ref, mpn))
            continue
        if part["assembly"] == "none":
            skipped.append(ref)
            continue
        key = part["lcsc"]
        entry = bom.setdefault(key, {"refs": [], "comment": fp.GetValue(), "footprint": fp.GetFPID().GetLibItemName().wx_str(), "class": part["class"]})
        entry["refs"].append(ref)
        if part["assembly"] in ("smt", "tht"):  # JLCPCB drops a BOM line whose designators have no placement
            pos = centre(fp)
            rot = (fp.GetOrientationDegrees() + float(part["rotation_offset"] or 0)) % 360
            cpl.append([ref, "%.4fmm" % pcbnew.ToMM(pos.x - origin.x), "%.4fmm" % -pcbnew.ToMM(pos.y - origin.y),
                        "Bottom" if fp.IsFlipped() else "Top", "%g" % rot])
    if problems:
        sys.exit("fab: " + "\n     ".join(problems))

    with open(os.path.join(out, name + "-bom-jlcpcb.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for lcsc, e in sorted(bom.items(), key=lambda kv: kv[1]["refs"][0]):
            w.writerow([e["comment"], ",".join(e["refs"]), e["footprint"], lcsc])
    with open(os.path.join(out, name + "-cpl-jlcpcb.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        w.writerows(cpl)

    layers = "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
    cli("pcb", "export", "gerbers", "--layers", layers, "--use-drill-file-origin", "--no-protel-ext", "-o", gerbers + "/", pcb)
    cli("pcb", "export", "drill", "--format", "excellon", "--drill-origin", "plot", "--excellon-units", "mm",
        "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", "-o", gerbers + "/", pcb)
    with zipfile.ZipFile(os.path.join(out, name + "-gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(gerbers)):
            z.write(os.path.join(gerbers, fn), fn)
    cli("pcb", "export", "step", "--drill-origin", "--subst-models", "--force", "-o", os.path.join(out, name + ".step"), pcb)

    unverified = sorted(r for e in bom.values() if e["class"] == "unverified" for r in e["refs"])
    print("fab: %d BOM lines, %d placements, %d Gerber/drill files, STEP -> %s" % (len(bom), len(cpl), len(os.listdir(gerbers)), os.path.relpath(out, REPO)))
    if skipped:
        print("fab: not assembled by JLCPCB: " + ", ".join(skipped))
    if unverified:
        print("fab: LCSC class unverified for " + ", ".join(unverified))


if __name__ == "__main__":
    main(sys.argv[1])
