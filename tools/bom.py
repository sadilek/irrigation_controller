"""Bill of materials for review: every footprint of the board, populated or not.

    tools/kipython tools/bom.py <board>

Writes build/<board>/<board>-bom.csv and a Markdown table next to it. Unlike the JLCPCB BOM of
tools/fab.py, this one also lists the footprints that stay empty, so the population options can be
checked against the schematic. Part numbers come from the footprints (Zener writes them there),
LCSC number, class and assembly type from lib/jlcpcb-parts.csv. A populated part without a row
there is an error.
"""
import csv
import os
import re
import sys

import pcbnew

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def field(fp, name):
    return fp.GetFieldText(name) if fp.HasField(name) else ""


def natural(ref):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def main(name):
    out = os.path.join(REPO, "build", name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(REPO, "lib", "jlcpcb-parts.csv"), newline="") as f:
        parts = {row["mpn"]: row for row in csv.DictReader(f)}
    board = pcbnew.LoadBoard(os.path.join(REPO, "boards", name, "eda", name + ".kicad_pcb"))

    lines, problems, no_part = {}, [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if fp.IsExcludedFromBOM():
            no_part.append(ref)
            continue
        mpn, populated = field(fp, "Mpn"), not fp.IsDNP()
        part = parts.get(mpn)
        if populated and part is None:
            problems.append("%s: part number %r has no row in lib/jlcpcb-parts.csv" % (ref, mpn))
            continue
        part = part or {"lcsc": "", "class": "", "assembly": "", "manufacturer": field(fp, "Manufacturer")}
        key = (mpn, populated, fp.IsFlipped())
        line = lines.setdefault(key, {
            "refs": [], "value": fp.GetValue(), "mpn": mpn, "manufacturer": field(fp, "Manufacturer"),
            "footprint": fp.GetFPID().GetLibItemName().wx_str(), "lcsc": part["lcsc"], "class": part["class"],
            "assembly": {"smt": "SMT", "tht": "through-hole", "none": "by hand", "": ""}[part["assembly"]],
            "side": "bottom" if fp.IsFlipped() else "top", "populated": "yes" if populated else "no"})
        line["refs"].append(ref)
    if problems:
        sys.exit("bom: " + "\n     ".join(problems))

    rows = sorted(lines.values(), key=lambda l: (l["populated"] != "yes", natural(min(l["refs"], key=natural))))
    columns = ["Populated", "Qty", "References", "Value", "Part number", "Manufacturer", "LCSC", "Class", "Assembly", "Side", "Footprint"]
    table = [[l["populated"], str(len(l["refs"])), " ".join(sorted(l["refs"], key=natural)), l["value"], l["mpn"], l["manufacturer"],
              l["lcsc"], l["class"], l["assembly"], l["side"], l["footprint"]] for l in rows]
    with open(os.path.join(out, name + "-bom.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        w.writerows(table)
    with open(os.path.join(out, name + "-bom.md"), "w") as f:
        f.write("| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n")
        for row in table:
            f.write("| " + " | ".join(row) + " |\n")

    placed = [l for l in rows if l["populated"] == "yes"]
    print("bom: %d lines populated (%d parts; %d basic, %d extended part types), %d lines not populated (%d footprints) -> %s" % (
        len(placed), sum(len(l["refs"]) for l in placed), sum(l["class"] == "basic" for l in placed),
        sum(l["class"] == "extended" for l in placed), len(rows) - len(placed),
        sum(len(l["refs"]) for l in rows if l["populated"] != "yes"), os.path.relpath(out, REPO)))
    print("bom: without a part (pads, holes, jumpers): " + " ".join(sorted(no_part, key=natural)))


if __name__ == "__main__":
    main(sys.argv[1])
