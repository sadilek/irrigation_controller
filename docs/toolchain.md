# Toolchain

How a board goes from source text to checked fabrication data and an enclosure that fits, without
opening KiCad or a CAD program. Verified end to end on `boards/throwaway` (5 V in, 3.3 V regulator,
LED) on 2026-11-13; the full chain runs in about 15 seconds.

## The chain

```
boards/<board>/<board>.zen ──check──▶ Zener compiler (nets, types, voltages)
        │ apply
        ▼
eda/<board>.kicad_sch ◀──arrange── schematic.py (where each symbol sits; optional)
        │ erc ──▶ erc.rpt      schematic ──▶ <board>-schematic.pdf      bom ──▶ <board>-bom.csv
eda/<board>.kicad_pcb  (footprints and nets, unplaced)
        │ layout   ◀── layout.py (positions) ◀── mech.json (outline, holes) ──▶ enclosure.py
        ▼                                                                          │ enclosure
eda/<board>.kicad_pcb  (outline, placed, routed by Freerouting)                    ▼
        │ drc ──▶ drc.rpt        render ──▶ render-top.png, render-bottom.png   base.step/.stl
        │ fab                                                                   lid.step/.stl
        ▼                                                                          │
fab/<board>-gerbers.zip, -bom-jlcpcb.csv, -cpl-jlcpcb.csv, <board>.step ──collide──┘
```

Sources are the `.zen` file, `schematic.py`, `layout.py`, `enclosure.py` and `mech.json`. Everything under `eda/`
is generated but committed, so the design opens in KiCad without any of these tools. Everything
under `build/` is generated and ignored by git.

## One command per output

Run from the repository root. `BOARD` defaults to `throwaway`.

| Command | Output |
|---|---|
| `make setup` | Pinned tools in `.tools/`, Python environment in `.venv/` |
| `make check` | Zener compile: connectivity, typed nets, voltage checks (no files written) |
| `make apply` | `boards/<board>/eda/`: KiCad schematic, board with footprints and nets, project file; ends with `make arrange` |
| `make arrange` | The schematic redrawn from `boards/<board>/schematic.py`, then compared with the Zener source; fails on any difference. Does nothing for a board without that file |
| `make bom` | `build/<board>/<board>-bom.csv` and `.md`: every footprint with part number, LCSC number, class, assembly type and side, populated or not |
| `make erc` | `build/<board>/erc.rpt`; fails on any violation |
| `make schematic` | `build/<board>/<board>-schematic.pdf` |
| `make layout` | Board outline, placement, ground zone and routed tracks in the `.kicad_pcb` |
| `make drc` | Zones filled, `build/<board>/drc.rpt`; fails on any violation or unconnected pad |
| `make render` | `build/<board>/render-top.png`, `render-bottom.png` |
| `make fab` | `build/<board>/fab/`: Gerber and drill zip, JLCPCB BOM, JLCPCB placement file, board STEP |
| `make enclosure` | `build/<board>/enclosure/`: `base` and `lid` as STEP and STL |
| `make collide` | Overlap volume of the populated board against each enclosure part; fails on overlap |
| `make all` | All of the above in order |
| `make verify` | The checks only, without touching committed files (what Obeya runs before landing) |
| `make selftest` | Lowers the lid into the pin header and expects `collide` to fail; renames a net label in the valve node schematic and expects the comparison with the source to fail |

## Schematic format: Zener

The schematic is written in **Zener** (`pcb` by Diode Computers, MIT license), not as KiCad files
by hand or by script.

Why Zener:

- **Reviewable source.** The throwaway board is 40 lines; a net is a name, a connection is an
  argument. A `.kicad_sch` describes the same thing as coordinates, UUIDs and embedded symbol copies
  (about 3,200 lines here), and a text diff of it shows geometry, not circuit changes.
- **It closes the one gap `kicad-cli` has.** KiCad 10 has no command for "update PCB from schematic".
  `pcb apply` does exactly that: it adds, removes and re-nets footprints and keeps placement and
  routing (tested: 30 routed segments survive an apply).
- **It still produces real KiCad files.** `pcb apply` writes a `.kicad_sch` and `.kicad_pcb` that
  KiCad 10 opens, checks and exports. The schematic PDF for review and all `kicad-cli` outputs come
  from those files, so KiCad remains the reference and the exit route.
- **Checks beyond ERC.** Nets are typed (`Power`, `Ground`, voltage ranges), parts are modules with
  parameters (`Resistor(value="1k", package="0603")`), and repeated circuits (four triac channels) are
  one module instantiated four times.
- **No private state.** Positions of schematic symbols are stored as comments in the `.zen` file.

Why not KiCad files directly: there is no supported headless API for creating schematics. Writing
S-expressions by script means inventing wire coordinates and symbol placement, keeping embedded
library symbols in sync by hand, and then still lacking the schematic-to-board update. The IPC API
needs a running KiCad window and has no schematic editing in 10.0. Every schematic edit would cost
more and be harder to review.

What Zener costs, and how the repo contains it:

| Risk | Containment |
|---|---|
| Young tool (0.4.x), released several times a week; the launcher follows the newest 0.4.x by itself | `Makefile` pins an exact toolchain (`ZENER`), every command runs through it |
| The toolchain downloads from Diode's server; `pcb bom` sends the part list to Diode's API | Toolchain is cached locally after the first run. `pcb bom` is not part of the chain; LCSC numbers come from `lib/jlcpcb-parts.csv` |
| If Zener disappears | `eda/` is committed and complete. The project continues in plain KiCad from that state |
| Only a subset of the KiCad libraries is bundled | Other symbols and footprints live in `lib/` (needed for LCSC parts anyway) |

## Schematic arrangement

`pcb apply` writes a schematic that is electrically complete but not drawn: symbols in a grid
sorted by part type, every pin ending in a net label. That is enough for the throwaway board and
useless for reviewing 80 parts. A board can therefore have a `schematic.py`, the counterpart of
`layout.py` for the schematic. It places symbols, draws wires between neighbouring pins, puts
labels and power symbols on the rest and frames the functional blocks
([`tools/schlayout.py`](../tools/schlayout.py)).

- The script decides positions only. Which pin is on which net is read from the netlist Zener
  writes for the board (`eda/default.net`).
- Three checks guard the drawing. `schlayout` refuses a drawing in which a net falls apart or two
  nets touch. Zener then compares the schematic with the source (`pcb build -D warnings`). KiCad's
  ERC runs on the result.
- Zener keeps positions, wires and texts of an existing schematic on the next apply and repairs
  only what the source changed. It rewrites the file in its own formatting, though, so `make apply`
  always ends with `make arrange`: the committed schematic is the script's output, byte for byte
  the same on every run.
- Symbols are addressed by their Zener path (`OUT1.R_GATE`), not by reference designator, because
  Zener renumbers references when parts are added.

## What is installed

`scripts/setup.sh` downloads pinned versions with SHA-256 checks into `.tools/` and changes nothing
else on the machine (no shell profile edits, no URL handlers, no global packages).

| Tool | Version | Role |
|---|---|---|
| KiCad | 10.0.1 (already installed, `/Applications`) | `kicad-cli` for ERC, DRC, exports, renders; its bundled Python (`pcbnew`) for layout scripts |
| Zener `pcb` | launcher 0.2.8, toolchain 0.4.101 | Schematic source, KiCad file generation |
| Freerouting | 2.5.0 (jar) with a private Temurin 25 JRE | Autorouter (Specctra DSN in, session file out) |
| build123d | 0.13 (via `uv`, Python 3.12) | Enclosure CAD, STEP import for the collision check |
| easyeda2kicad | 1.0.1 (via `uvx`) | `scripts/fetch-lcsc.sh`: symbol, footprint, STEP model of an LCSC part |
| Konnect | 0.13.0 | KiCad MCP server; installed, not part of the chain (see below) |

## Libraries and the JLCPCB mapping

See [`lib/README.md`](../lib/README.md). In short: passives and connectors come from Zener's bundled
KiCad subset; other standard symbols and footprints are copied from the KiCad installation into
`lib/kicad/`; part-specific footprints are fetched per LCSC number into `lib/lcsc/` with the 3D
model embedded in the footprint file; `lib/jlcpcb.zen` holds design rules for JLCPCB's two-layer process; and
`lib/jlcpcb-parts.csv` maps each manufacturer part number to the LCSC number, assembly type and
rotation correction that `make fab` writes into the BOM and placement file.

## What does not hold up

Found while running the chain. Ordered by how much they matter for the real boards.

1. **The autorouter's result is unreviewed copper.** Freerouting connects everything and passes
   DRC, but it knows nothing about current, creepage between 24 VAC and logic, or where surge
   current should flow. On the throwaway board that is harmless. For the valve node, mains-side and
   protection nets need track widths, clearances and keep-outs set as rules *before* routing (net
   classes in `lib/jlcpcb.zen`, custom DRC rules in the KiCad project), and the critical nets may
   have to be routed by explicit coordinates in `layout.py`. Net classes beyond `Default` and their
   assignment to nets from Zener are not exercised yet.
2. **Placement is by coordinates the worker picks.** There is no auto-placer. `layout.py` lists a
   position per part; the script refuses to run if a part has none. This is workable for 30–60
   parts but each placement round needs a render to look at, and DRC only catches overlaps, not bad
   placement.
3. **KiCad's ERC is weakened on a Zener schematic.** Two rules are switched off in the project
   file: `lib_symbol_issues` (Zener embeds symbols without a library table) and
   `power_pin_not_driven` (Zener has no `PWR_FLAG`; a power net without a source is caught by
   Zener's typed nets instead). Pin-type conflicts and unconnected pins are still checked.
   The arrangement step adds a comparison of the drawn schematic with the Zener source.
   Schematic-parity in DRC is not used: Zener names local nets `LED_A` on the board and `/LED_A` in
   the schematic, so every local net is reported as a mismatch.
4. **Part numbers are not in the schematic.** Zener writes `Mpn` and `Manufacturer` to the board's
   footprints only. The schematic PDF shows values; the BOM is a separate file (`make bom`). A
   schematic review needs both side by side.
5. **LCSC data cannot be fully verified offline.** The community search API (jlcsearch) answered
   half the lookups with errors and reports basic/extended inconsistently. Three of the five
   throwaway parts are therefore marked `unverified`. Before an order, class, stock and price need
   a check on jlcpcb.com. Rotation corrections for JLCPCB's placement can only be found in JLCPCB's
   own preview; `rotation_offset` in the parts file records them once found.
6. **Fetched LCSC parts are raw material.** easyeda2kicad writes a KiCad 6 file format, absolute
   paths into footprints, 3D models offset by 0.3 mm, and pins of type "unspecified".
   `scripts/fetch-lcsc.sh` repairs the first three; pin types and the footprint itself must be
   checked against the datasheet by the worker for every part (done for the AMS1117).
7. **KiCad's Python interface (SWIG) is fragile.** It is officially deprecated in favour of the IPC
   API. In 10.0.1, freeing an item that was removed from a board corrupts the type information for
   the rest of the process; `tools/kilayout.py` works around it. It is still the only interface that
   works without a KiCad window, and Zener itself depends on it. A KiCad upgrade can break layout
   scripts; rerun `make all` on the throwaway board after any upgrade.
8. **The planned MCP route does not hold.** The plan named Konnect on the KiCad IPC API. Konnect was
   archived on 2026-11-02 and continues as a closed-source commercial product (free for hobby and
   open hardware); 0.13.0 is the last AGPL release. Independent of that, the IPC API only works
   while a KiCad window is open, which a background worker cannot rely on. The chain therefore uses
   scripts on `pcbnew` instead. Konnect 0.13.0 is installed at `.tools/bin/konnect` but not
   registered and not tested live: starting it was blocked by the session's permission rules. To
   try it: `claude mcp add --scope project konnect -- .tools/bin/konnect` (never run `konnect` bare
   in a terminal: it then installs skills and hooks into `~/.claude`).
9. **Freerouting's native binary is broken.** The `freerouting-cli` 2.5.0 build for macOS crashes on
   every board and then hangs. The jar with a Java runtime works; setup installs a private JRE.
10. **Layout output is not byte-stable.** Every `make layout` assigns new UUIDs, so the committed
    `.kicad_pcb` changes in git even when nothing moved. Commit it only after intended changes.
11. **The collision check finds overlap, not clearance.** A part 0.05 mm from a wall passes. It
    also reports solids by position, not by reference designator. Minimum-distance checking and
    names are small additions for the enclosure work.
12. **Zener joins pins that share a name.** A symbol with two pins called `NC` gets one net for
    both, and the board would connect them. Copied symbols get distinct pin names
    (`scripts/copy-kicad.py … 3=NC3 5=NC5`). Generic modules (`Tvs`) also write their own value
    text ("15V TVS Diode"); a part whose value should be its type is a plain `Component`.
13. **Small Zener rough edges.** `copper_finish` documents `"HASL Lead-free"` but only accepts
    `"HAL lead-free"`; default design rules (0.09 mm) are finer than JLCPCB's standard process and
    must be overridden (`lib/jlcpcb.zen`); a shared library must be its own package with a `pcb.toml`.

Not exercised on the throwaway board: parts on the bottom side, more than one net class, panels,
through-hole assembly by JLCPCB, and an actual upload to JLCPCB.
