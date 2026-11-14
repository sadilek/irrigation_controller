#!/usr/bin/env python3
"""Copy symbols and footprints from the KiCad installation into lib/kicad/.

    scripts/copy-kicad.py sym <Library>:<Symbol> [<new name>] [<pin number>=<pin name> ...]
    scripts/copy-kicad.py fp  <Library>:<Footprint>

Zener does not read KiCad's library tables, so every symbol and footprint a board uses beyond
Zener's bundled subset is a file in this repository. A symbol becomes one file,
lib/kicad/symbols/<name>.kicad_sym. A symbol that extends another one in KiCad's library is
flattened: the copy carries the parent's graphics and pins and its own properties. Footprints go to
lib/kicad/footprints.pretty/ unchanged; their 3D models stay references into the KiCad installation
(${KICAD10_3DMODEL_DIR}), which kicad-cli resolves.

`<new name>` renames the copy. Use it only for a part with the same package and pin assignment as
the library part, and say so in lib/README.md. `<pin number>=<pin name>` renames pins: Zener
addresses pins by name and refuses a symbol in which two pins share one (KiCad's BAV99).
"""
import os
import re
import shutil
import sys

SHARE = os.environ.get("KICAD_SHARE", "/Applications/KiCad/KiCad.app/Contents/SharedSupport")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "lib", "kicad")


def block_end(text, start):
    """Index after the parenthesis that closes the one at `start`. Quoted strings are skipped."""
    depth, i, in_string = 0, start, False
    while i < len(text):
        c = text[i]
        if in_string:
            if c == "\\":
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced parentheses")


def children(block):
    """Top-level child expressions of one `(symbol ...)` block, as text."""
    out, i = [], block.index("(", 1) if "(" in block[1:] else len(block)
    while i < len(block) - 1:
        if block[i] == "(":
            end = block_end(block, i)
            out.append(block[i:end])
            i = end
        else:
            i += 1
    return out


def find_symbol(text, name):
    m = re.search(r'^\t\(symbol "%s"' % re.escape(name), text, re.M)
    if not m:
        sys.exit("symbol %r not found" % name)
    start = m.start() + 1
    return text[start:block_end(text, start)]


def head(expr):
    return re.match(r"\((\S+)", expr).group(1)


def prop_name(expr):
    return re.match(r'\(property "([^"]*)"', expr).group(1)


def flat_children(text, name):
    """Child expressions of a symbol with its chain of `extends` parents folded in."""
    kids = children(find_symbol(text, name))
    parent = next((k for k in kids if head(k) == "extends"), None)
    if not parent:
        return kids
    parent_name = re.search(r'"([^"]*)"', parent).group(1)
    base = flat_children(text, parent_name)
    own = {prop_name(k): k for k in kids if head(k) == "property"}
    merged = []
    for k in base:
        if head(k) == "property":
            merged.append(own.pop(prop_name(k), k))
        elif head(k) == "symbol":
            merged.append(k.replace('(symbol "%s_' % parent_name, '(symbol "%s_' % name, 1))
        else:
            merged.append(k)
    # properties the parent does not have go in front of the first unit
    at = next(i for i, k in enumerate(merged) if head(k) == "symbol")
    merged[at:at] = list(own.values())
    return merged


def rename_pins(unit, names):
    def one(m):
        number = re.search(r'\(number "([^"]*)"', m.group(0)).group(1)
        if number not in names:
            return m.group(0)
        return re.sub(r'\(name "[^"]*"', '(name "%s"' % names[number], m.group(0), count=1)

    out, i = "", 0
    for m in re.finditer(r"\(pin ", unit):
        end = block_end(unit, m.start())
        out += unit[i:m.start()] + one(re.match(r"(?s).*", unit[m.start():end]))
        i = end
    return out + unit[i:]


def copy_symbol(spec, new_name=None, pin_names=None):
    lib, name = spec.split(":", 1)
    with open(os.path.join(SHARE, "symbols", lib + ".kicad_sym")) as f:
        text = f.read()
    kids = flat_children(text, name)
    target = new_name or name
    if target != name:
        kids = [k.replace('(symbol "%s_' % name, '(symbol "%s_' % target, 1) if head(k) == "symbol" else k for k in kids]
        # The copy describes another part: keep nothing that names the original's package or datasheet.
        values = {"Value": target, "Footprint": "", "Datasheet": "", "Description": "Pin assignment of %s" % spec}
        kids = [re.sub(r'(\(property "[^"]*" )"[^"]*"', lambda m: '%s"%s"' % (m.group(1), values[prop_name(k)]), k, count=1)
                if head(k) == "property" and prop_name(k) in values else k for k in kids]
    if pin_names:
        kids = [rename_pins(k, pin_names) if head(k) == "symbol" else k for k in kids]
    version = re.search(r"\(version \d+\)", text).group(0)
    body = "\n".join("\t\t" + k for k in kids)
    out = '(kicad_symbol_lib\n\t%s\n\t(generator "copy-kicad")\n\t(symbol "%s"\n%s\n\t)\n)\n' % (version, target, body)
    os.makedirs(os.path.join(OUT, "symbols"), exist_ok=True)
    path = os.path.join(OUT, "symbols", target + ".kicad_sym")
    with open(path, "w") as f:
        f.write(out)
    print(os.path.relpath(path, REPO))


def copy_footprint(spec):
    lib, name = spec.split(":", 1)
    src = os.path.join(SHARE, "footprints", lib + ".pretty", name + ".kicad_mod")
    if not os.path.exists(src):
        sys.exit("footprint %r not found" % spec)
    os.makedirs(os.path.join(OUT, "footprints.pretty"), exist_ok=True)
    dst = os.path.join(OUT, "footprints.pretty", name + ".kicad_mod")
    shutil.copyfile(src, dst)
    print(os.path.relpath(dst, REPO))


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("sym", "fp"):
        sys.exit(__doc__)
    if sys.argv[1] == "sym":
        rest = sys.argv[3:]
        copy_symbol(sys.argv[2], next((a for a in rest if "=" not in a), None), dict(a.split("=", 1) for a in rest if "=" in a))
    else:
        copy_footprint(sys.argv[2])
