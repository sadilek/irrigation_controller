# Part libraries

| Path | Content |
|---|---|
| `kicad/` | Symbols (`symbols/`, one file each) and footprints (`footprints.pretty/`) copied from the KiCad installation with `scripts/copy-kicad.py`. First choice for anything KiCad's library has: the pin types are right, so ERC means something. 3D models stay references into the KiCad installation. |
| `lcsc/` | Symbols and footprints fetched from LCSC/EasyEDA with `scripts/fetch-lcsc.sh C<number>`. STEP models are embedded in the footprint files, so there are no model paths to configure. Zener package (`pcb.toml`). |
| `jlcpcb.zen` | Design rules and net classes for the JLCPCB two-layer process; boards pass it as `Board(config=JLCPCB_2L)`. |
| `jlcpcb-parts.csv` | The mapping from manufacturer part number to LCSC number that `make fab` uses for the JLCPCB BOM and placement file. |

Standard KiCad symbols and footprints come from two places. Zener bundles a subset (passives, LEDs,
pin headers, mounting holes, test points, …) behind its generics, e.g. `@stdlib/generics/Resistor.zen`.
Anything else is copied from the KiCad installation into a library directory here and referenced with
`Symbol(library=…)` and `footprint=File(…)`; Zener does not read KiCad's global library tables.

Two fetched footprints are changed by hand, each against the manufacturer's drawing
([`docs/valve-node-layout.md`](../docs/valve-node-layout.md), "Deviations"). Fetching them again
with `scripts/fetch-lcsc.sh` overwrites that.

| Footprint | Changed |
|---|---|
| `RJ45-TH_RJHSE-5080` | Pads 1.4 mm with 0.9 mm holes (fetched: 1.6 and 1.0); the two pegs are unplated holes of 3.25 mm (fetched: plated, 3.3 mm, no pad); silkscreen ends inside the board edge |
| `CONN-TH_2P-P5.08_KF2EDGR-5.08-2P` | Silkscreen reduced to the outline behind the board edge, clear of the pads |

A board keeps the footprint it was created with: after changing a footprint file, delete the
board file as described in `CLAUDE.md`, "Lessons learned".

## `kicad/`: copied and renamed symbols

`scripts/copy-kicad.py sym <Library>:<Symbol> [<new name>] [<pin>=<name> ...]` and
`scripts/copy-kicad.py fp <Library>:<Footprint>`. Four symbols are copies under another name and one has renamed pins,
because KiCad has no symbol for the part but one with the same package and pin assignment. Each
was checked against the part's datasheet ([`docs/valve-node-schematic.md`](../docs/valve-node-schematic.md)).

| Symbol | Copied from | Changed |
|---|---|---|
| `THVD2410DR` | `Interface_UART:THVD1450DR` | name |
| `T410-600B` | `Triac_Thyristor:BT136-600` | name |
| `EL3053` | `Relay_SolidState:MOC3052M` | name; pins 3 and 5 named `NC3` and `NC5`, because Zener joins pins that share a name into one net |
| `LTV-814S` | `Isolator:LTV-814` | name |
| `BAV99` | `Diode:BAV99` | pins named `A`, `K`, `COM`; KiCad's names repeat |

## `jlcpcb-parts.csv`

Every populated part on a board must have a row, otherwise `make fab` stops.

| Column | Meaning |
|---|---|
| `mpn`, `manufacturer` | As written in the `.zen` source (`mpn=`, `Part(mpn=…)`). The join key is `mpn`. |
| `lcsc` | LCSC part number that JLCPCB places. |
| `class` | `basic`, `extended` (per-part setup fee) or `unverified`. Confirm on jlcpcb.com/parts before an order; community search mirrors are incomplete. |
| `assembly` | `smt` (in BOM and placement file), `tht` (in BOM, through-hole assembly) or `none` (left out, soldered by hand). |
| `rotation_offset` | Degrees added to the KiCad rotation in the placement file, for parts whose JLCPCB reel orientation differs from the KiCad footprint. Found in JLCPCB's placement preview, then recorded here so the fix is not repeated by hand per order. |
