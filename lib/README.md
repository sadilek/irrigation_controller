# Part libraries

| Path | Content |
|---|---|
| `lcsc/` | Symbols and footprints fetched from LCSC/EasyEDA with `scripts/fetch-lcsc.sh C<number>`. STEP models are embedded in the footprint files, so there are no model paths to configure. Zener package (`pcb.toml`). |
| `jlcpcb.zen` | Design rules and net classes for the JLCPCB two-layer process; boards pass it as `Board(config=JLCPCB_2L)`. |
| `jlcpcb-parts.csv` | The mapping from manufacturer part number to LCSC number that `make fab` uses for the JLCPCB BOM and placement file. |

Standard KiCad symbols and footprints come from two places. Zener bundles a subset (passives, LEDs,
pin headers, mounting holes, test points, …) behind its generics, e.g. `@stdlib/generics/Resistor.zen`.
Anything else is copied from the KiCad installation into a library directory here and referenced with
`Symbol(library=…)` and `footprint=File(…)`; Zener does not read KiCad's global library tables.

## `jlcpcb-parts.csv`

Every populated part on a board must have a row, otherwise `make fab` stops.

| Column | Meaning |
|---|---|
| `mpn`, `manufacturer` | As written in the `.zen` source (`mpn=`, `Part(mpn=…)`). The join key is `mpn`. |
| `lcsc` | LCSC part number that JLCPCB places. |
| `class` | `basic`, `extended` (per-part setup fee) or `unverified`. Confirm on jlcpcb.com/parts before an order; community search mirrors are incomplete. |
| `assembly` | `smt` (in BOM and placement file), `tht` (in BOM, through-hole assembly) or `none` (left out, soldered by hand). |
| `rotation_offset` | Degrees added to the KiCad rotation in the placement file, for parts whose JLCPCB reel orientation differs from the KiCad footprint. Found in JLCPCB's placement preview, then recorded here so the fix is not repeated by hand per order. |
