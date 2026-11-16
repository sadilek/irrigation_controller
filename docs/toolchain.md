# Toolchain

How a board goes from source text to checked fabrication data and an enclosure that fits, without
opening KiCad or a CAD program. Verified end to end on `boards/throwaway` (5 V in, 3.3 V regulator,
LED) on 2026-11-13; the full chain runs in about 15 seconds. The valve node (60 footprints) runs
through the same chain in about two minutes.

## The chain

```
boards/<board>/<board>.zen ──check──▶ Zener compiler (nets, types, voltages)
        │ apply
        ▼
eda/<board>.kicad_sch ◀──arrange── schematic.py (where each symbol sits; optional)
        │ erc ──▶ erc.rpt      schematic ──▶ <board>-schematic.pdf      bom ──▶ <board>-bom.csv
eda/<board>.kicad_pcb  (footprints and nets, unplaced)
        │ layout   ◀── layout.py (positions, rules, tracks) ◀── mech.json ──▶ enclosure.py
        ▼                                                                          │ enclosure
eda/<board>.kicad_pcb, .kicad_dru  (outline, placed, routed, design rules)         ▼
        │ drc ──▶ drc.rpt        render, plots ──▶ render-*.png, plots/*.svg    base.step/.stl
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
| `make layout` | Board outline, placement, zones, rule areas, silkscreen texts and tracks in the `.kicad_pcb`; net classes in the `.kicad_pro`, custom rules in the `.kicad_dru` |
| `make drc` | Zones filled, `build/<board>/drc.rpt`; fails on any violation or unconnected pad |
| `make render` | `build/<board>/render-top.png`, `render-bottom.png`, `render-angle.png` |
| `make plots` | `build/<board>/plots/`: copper per side and an assembly drawing with reference designators (SVG), copper coloured by net class (`classes.svg`), and `<board>-1to1.pdf`, the board at true size for a paper test fit |
| `make fab` | `build/<board>/fab/`: Gerber and drill zip, JLCPCB BOM, JLCPCB placement file (surface-mount and through-hole parts), board STEP |
| `make enclosure` | `build/<board>/enclosure/`: the enclosure parts as STEP. Throwaway board: STL beside them. Valve node: STL per printed part in `print/` (with `board-dummy.stl` for a test fit), pictures in `views/` (with the real board once `make fab` has run), and `envelope.step` (about 40 s) |
| `make collide` | Overlap volume of the populated board against each enclosure part; fails on overlap. Without a board STEP it uses `envelope.step`: the outline and connectors from `mech.json` as blocks. If the enclosure script wrote `plugs.step` (mated plugs as blocks), those are checked as well |
| `make all` | All of the above in order |
| `make verify` | The checks only, without touching committed files (what Obeya runs before landing) |
| `make selftest` | Lowers the lid into the pin header (throwaway board) and into the bus jacks (valve node), moves the programming plug off its pins and fills the pin pockets of the board supports (valve node), and expects `collide` to fail each time; renames a net label in the valve node schematic and expects the comparison with the source to fail; draws a ground track near 24 VAC copper, under an optocoupler and under a screw head on a copy of the valve node board and expects DRC to name the rule each time; builds the firmware simulator with a wrong bus-loss timeout and expects the bus test to fail |
| `make firmware`, `firmware-test`, `firmware-sim`, `firmware-bench`, `firmware-upload` | Valve node firmware: hex file, tests on the computer, simulated bus, test bench in the browser, programming. Not part of `make all`; see [`valve-node-firmware.md`](valve-node-firmware.md#build-test-program) |

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
- For such a board `make apply` deletes the schematic, lets Zener create it anew and ends with
  `make arrange`: the committed schematic is the script's output, byte for byte the same on every
  run. Zener can also update an existing schematic in place and keep its arrangement, but that
  path is not used: it reformats the file, and after parts were removed from the source it left a
  library symbol renamed (`EL3053_1`) with its instances pointing at the old name.
- Symbols are addressed by their Zener path (`OUT1.R_GATE`), not by reference designator, because
  Zener renumbers references when parts are added.

## Routing

A board's `layout.py` places every part by coordinates and then has three ways to make copper,
all in [`tools/kilayout.py`](../tools/kilayout.py):

| | What | Used for |
|---|---|---|
| `track()`, `via()`, `zone()` | Copper drawn by coordinates | Everything where the path matters: 24 VAC, the bus pass-through, surge paths, copper areas |
| `router()` | [`tools/gridroute.py`](../tools/gridroute.py): a grid router of this repository. 0.1 mm grid, two layers, 45° bends, shortest path first, one net after the other in the order given, no second attempt. `fanout()` leads the pins of a fine-pitch package out to twice their pitch first | The logic side of the valve node |
| `autoroute()` | Freerouting round trip (Specctra DSN out, session in). Scripted tracks are exported as fixed and put back as drawn | The throwaway board |

Design rules belong to the board, not to the script that routes it. `write_rules()` puts net
classes and their net-name patterns into the KiCad project and custom rules into
`<board>.kicad_dru`; `kicad-cli pcb drc` then checks them, whoever drew the copper. The valve
node's 3 mm between 24 VAC and logic is such a rule, with a named area for the one exception
([`valve-node-layout.md`](valve-node-layout.md)).

The grid router knows one clearance and no custom rules. A board keeps it away from copper with a
larger clearance through the region it hands over. It stops the build when a net finds no way
and prints the obstacle map around the pads it could not reach.

## What is installed

`scripts/setup.sh` downloads pinned versions with SHA-256 checks into `.tools/` and changes nothing
else on the machine (no shell profile edits, no URL handlers, no global packages).

| Tool | Version | Role |
|---|---|---|
| KiCad | 10.0.1 (already installed, `/Applications`) | `kicad-cli` for ERC, DRC, exports, renders; its bundled Python (`pcbnew`) for layout scripts |
| Zener `pcb` | launcher 0.2.8, toolchain 0.4.101 | Schematic source, KiCad file generation |
| Freerouting | 2.5.0 (jar) with a private Temurin 25 JRE | Autorouter (Specctra DSN in, session file out) |
| build123d | 0.13 (via `uv`, Python 3.12) | Enclosure CAD, STEP import for the collision check; `tools/render3d.py` draws the enclosure pictures with the numpy and Pillow it brings along |
| easyeda2kicad | 1.0.1 (via `uvx`) | `scripts/fetch-lcsc.sh`: symbol, footprint, STEP model of an LCSC part |
| Konnect | 0.13.0 | KiCad MCP server; installed, not part of the chain (see below) |
| avr-gcc, avrdude | 14.4.0 with avr-libc 2.2.1; 8.3 (Homebrew, not installed by `setup.sh`: `brew tap osx-cross/avr && brew install osx-cross/avr/avr-gcc@14 avrdude`) | Firmware build and programming. Tests and simulator use the computer's own C++ compiler |

## Libraries and the JLCPCB mapping

See [`lib/README.md`](../lib/README.md). In short: passives and connectors come from Zener's bundled
KiCad subset; other standard symbols and footprints are copied from the KiCad installation into
`lib/kicad/`; part-specific footprints are fetched per LCSC number into `lib/lcsc/` with the 3D
model embedded in the footprint file; `lib/jlcpcb.zen` holds design rules for JLCPCB's two-layer process; and
`lib/jlcpcb-parts.csv` maps each manufacturer part number to the LCSC number, assembly type and
rotation correction that `make fab` writes into the BOM and placement file.

## What does not hold up

Found while running the chain. Ordered by how much they matter for the real boards.

1. **An autorouter's result is unreviewed copper, and Freerouting did not finish the real board.**
   It knows nothing about current, creepage between 24 VAC and logic, or where surge current
   should flow. On the throwaway board that is harmless. On the valve node (2026-11-14) the
   critical nets are drawn by coordinates, and for the rest Freerouting 2.5.0 left 8 to 13
   connections open around the 0.4 mm pitch microcontroller in every run and wrote three tracks of
   0.12 mm, below the 0.15 mm minimum. More passes, a 0.2 mm default width and pre-drawn stubs
   did not change that. The valve node therefore uses `tools/gridroute.py` ("Routing" above). That
   router is small and crude: no rip-up, one clearance, pad outlines as rectangles; a placement
   change can leave a net without a way, and the fix is then by hand in `layout.py`. Zener cannot
   assign nets to classes other than by impedance, so net classes come from `layout.py`.
2. **Placement is by coordinates the worker picks.** There is no auto-placer. `layout.py` lists a
   position per part; the script refuses to run if a part has none. This worked for the valve
   node's 60 footprints, but each placement round needs a picture to look at (`make plots` is
   faster than `make render`), and DRC only catches overlaps, not bad placement. Two identical
   connectors whose pins are passed through need their wire order planned before anything is
   placed ([`valve-node-layout.md`](valve-node-layout.md), "The pass-through").
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
    names are small additions for the enclosure work. It is also blind where two thread solids
    meet: OpenCascade returns wrong volumes for that pair, so nut against boss is right by
    construction only ([`valve-node-enclosure.md`](valve-node-enclosure.md), "Checks").
12. **Zener joins pins that share a name.** A symbol with two pins called `NC` gets one net for
    both, and the board would connect them. Copied symbols get distinct pin names
    (`scripts/copy-kicad.py … 3=NC3 5=NC5`). Generic modules (`Tvs`) also write their own value
    text ("15V TVS Diode"); a part whose value should be its type is a plain `Component`.
13. **Small Zener rough edges.** `copper_finish` documents `"HASL Lead-free"` but only accepts
    `"HAL lead-free"`; default design rules (0.09 mm) are finer than JLCPCB's standard process and
    must be overridden (`lib/jlcpcb.zen`); a shared library must be its own package with a `pcb.toml`.

14. **A rule area that forbids tracks is not enough.** KiCad 10.0.1's DRC did not report a track
    drawn through one on the valve node; zones did stay out. Keep-outs are therefore repeated as
    `disallow` rules in the board's `.kicad_dru`, and `make selftest` proves each one by drawing
    a track into it on a copy of the board.
15. **Zener keeps the footprint a board was created with.** A changed footprint file in `lib/`
    reaches the board only after `eda/<board>.kicad_pcb` and `eda/snapshot.layout.json` are
    deleted and `make apply layout` has run. `pcb apply` also resets the `Default` net class of
    the KiCad project from `lib/jlcpcb.zen` on every run; other classes survive.
16. **Silkscreen from fetched footprints crosses pads and board edges, and a fetched 3D model
    can sit turned.** Three connector footprints were corrected by hand
    ([`lib/README.md`](../lib/README.md)). The turned model passed the collision check.
17. **The collision check knows only what is modelled.** The valve node's pluggable terminals
    passed it while their plugs had no room; nobody had modelled a plug. Mated plugs are now
    blocks the enclosure script writes, for the connectors that have them.

Not exercised on either board: parts on the bottom side, panels, through-hole assembly by JLCPCB,
and an actual upload to JLCPCB.
