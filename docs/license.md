# Licenses

Decided by the owner on 2026-11-14. The repository is still private; publishing is a separate
decision.

Copyright (c) 2026 The irrigation_controller authors. The full texts are in [`LICENSES/`](../LICENSES/).

| Content | License | SPDX |
|---|---|---|
| Hardware: board sources and generated KiCad files (`boards/`), `lib/` except fetched LCSC parts, enclosure models | CERN Open Hardware Licence v2, Permissive | `CERN-OHL-P-2.0` |
| Software: firmware, `tools/`, `scripts/`, `Makefile` | MIT | `MIT` |
| Documentation (`docs/`, READMEs) | Creative Commons Attribution 4.0 | `CC-BY-4.0` |

## Why permissive

- The design is a small, purpose-built garden controller. Its value to others is as a reference
  and a starting point; a reciprocal license (CERN-OHL-S, GPL) mostly deters that reuse and is only
  worth it if someone would enforce it.
- CERN-OHL-P is written for hardware: it covers the patent grant and the "as is" disclaimer for
  physical products that MIT does not address, and it only asks for attribution notices to be kept.
- MIT for software matches Zener, build123d's ecosystem and ESPHome examples, and keeps firmware
  snippets reusable without questions.
- The alternative, if derived boards should stay open: `CERN-OHL-S-2.0` for hardware and `GPL-3.0`
  for firmware. That is a deliberate choice for reciprocity, with the cost above.

## What must be settled before publishing

1. **Fetched LCSC/EasyEDA parts** (`lib/lcsc/`): symbols, footprints and 3D models converted from
   EasyEDA's library. Whether their terms allow redistribution under an open license has not been checked.
   Options: redraw the few parts needed from datasheets (clean), or keep `lib/lcsc/` out of the
   published repository and document `scripts/fetch-lcsc.sh` as a build step.
2. **KiCad library content** copied into the generated files (`boards/*/eda/`) is CC-BY-SA 4.0 with
   KiCad's exception that designs using the libraries are not bound by it. No action needed.
3. **Git history.** Commits carry the author's name and e-mail address. Publish with the existing
   history only if that is acceptable; otherwise publish a squashed history.
4. **Private data.** Rerun the check from `CLAUDE.md` over the whole history, not only the tree.
5. **Tools are not redistributed.** Freerouting (GPL-3.0) and Konnect (AGPL-3.0) are downloaded by
   `scripts/setup.sh` and are not part of the repository, so their licenses do not affect it.

## Conventions

- New source files do not need a header; the table above assigns a license by path. A file that
  leaves the repository on its own (a published STL, a firmware release) carries an
  `SPDX-License-Identifier` line or a note naming its license.
- `lib/lcsc/` is not covered by these licenses (see point 1 above).
