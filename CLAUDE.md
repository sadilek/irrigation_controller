# CLAUDE.md

Guidance for Claude Code (and any other agent or contributor) working in this repository.

## Project overview

Garden irrigation hardware: two custom boards and their 3D-printed enclosures.

- **Valve node:** sits in a valve box in the ground, switches 24 VAC solenoid valves, talks
  Modbus RTU over RS485 on a buried cable.
- **Controller:** sits in a dry shed, powers the bus, bridges it to Home Assistant via ESPHome.

Boards are written as code (Zener), generated into KiCad 10 files, placed and routed by script, and
fabricated and assembled by JLCPCB. Enclosures are modelled in build123d. An agent does all of it
in files; the owner reviews each board at three hold points (specification, schematic, layout and
enclosure) and places every order himself.

**Status:** toolchain proven on a throwaway board. The valve node has a specification
([`docs/valve-node-spec.md`](docs/valve-node-spec.md)); its schematic waits for the owner's sign-off.
No real board exists yet.

## Rules that are not negotiable

- **English only.** Everything that stays in the repository is English: docs, code, comments,
  commit messages, file names, schematic and board annotations. The project may be published.
- **No private data.** No IP addresses, Wi-Fi names, credentials, document IDs, personal names,
  home directory paths or garden layout beyond what the design needs. Firmware secrets go through
  ESPHome `!secret` and stay out of git. Before committing, run
  `git grep -n -I -e '/Users/' -e '192\.168' -e '@gmail'` and expect no hit except this line.
- **Only the owner orders.** Never upload to or order from JLCPCB or any shop.
- **Hold points.** A board's next stage does not start before the owner signed off the previous
  one. Each hold point shows the reasoning, not just the result; the hard part of this project is
  switching 24 VAC and surviving surges on a long buried cable, not routing.
- **Do not edit generated files by hand.** `boards/*/eda/` is written by `make apply`,
  `make layout` and `make drc`. Change the `.zen` source, `layout.py` or `mech.json` instead.

## Commands

```bash
make setup                 # once per checkout: pinned tools into .tools/, Python env into .venv/
make all BOARD=<board>     # whole chain: source -> KiCad files -> ERC -> layout -> DRC -> fab -> enclosure -> collision
make verify BOARD=<board>  # all checks, no committed file is modified
make help                  # every target with its output
```

One target per output; the table is in [`docs/toolchain.md`](docs/toolchain.md). `BOARD` defaults
to `throwaway`, the smoke-test board: after changing a tool version or anything in `tools/`, run
`make all && make selftest` on it before touching a real board.

## Layout

| Path | Content |
|---|---|
| `boards/<board>/<board>.zen` | Schematic source (Zener) |
| `boards/<board>/mech.json` | Board outline and mounting holes: the one interface between board and enclosure |
| `boards/<board>/layout.py` | Placement and routing script (runs in KiCad's Python via `tools/kipython`) |
| `boards/<board>/enclosure.py` | Enclosure model (build123d, runs in the project venv via `uv run`) |
| `boards/<board>/eda/` | Generated KiCad project, committed so the design opens without the toolchain |
| `lib/` | Shared parts: LCSC symbols and footprints, JLCPCB design rules, part-number mapping ([`lib/README.md`](lib/README.md)) |
| `tools/` | Shared scripts: layout helpers, fabrication outputs, collision check |
| `scripts/` | Setup and part fetching |
| `docs/` | Durable documentation (Markdown) |
| `build/` | Generated outputs, ignored by git |

## Where to read more

| Question | File |
|---|---|
| How does the chain work, what does each command produce, where is it weak? | [`docs/toolchain.md`](docs/toolchain.md) |
| What is on the bus: wiring, addresses, registers, timing? | [`docs/bus-protocol.md`](docs/bus-protocol.md) |
| What does the installed system look like, what are its weaknesses, what is still unknown? | [`docs/existing-system.md`](docs/existing-system.md) |
| What does the valve node have to do, which parts does it use and why? | [`docs/valve-node-spec.md`](docs/valve-node-spec.md) |
| Why Zener and not KiCad files? | [`docs/toolchain.md`](docs/toolchain.md) "Schematic format" |
| How do I add a part and map it to an LCSC number? | [`lib/README.md`](lib/README.md) |
| Which license covers what, and what blocks publication? | [`docs/license.md`](docs/license.md) |

## Cross-cutting facts

- Two Python interpreters, on purpose. `pcbnew` exists only in KiCad's bundled Python 3.9
  (`tools/kipython`); build123d needs the project venv (Python 3.12, `uv run`). A script uses one or
  the other, never both. They exchange data through files (`mech.json`, STEP).
- Coordinates: `mech.json` and `layout.py` use millimetres from the board's top-left corner, x
  right, y down (KiCad). STEP files and `enclosure.py` use the same origin with y up, so a KiCad
  point (x, y) is (x, −y) there. The board's bottom face is z = 0.
- `kicad-cli` writes its results to stdout and Fontconfig noise to stderr. The Makefile drops
  stderr; when a kicad-cli step fails without a message, rerun it by hand without `2>/dev/null`.
- The Zener toolchain version is pinned in the `Makefile` (`ZENER`). Always call Zener through
  `make` or as `.tools/bin/pcb +<version>`; a bare `pcb` follows the newest 0.4.x release.
- Part numbers: every populated part carries `mpn=` (or `Part(mpn=…)`) in the `.zen` source and a
  row in `lib/jlcpcb-parts.csv`. `make fab` fails otherwise.
- KiCad ERC runs with two rules disabled (`lib_symbol_issues`, `power_pin_not_driven`), set in each
  board's `.kicad_pro`; the reason is in `docs/toolchain.md`. Do not disable further rules to get a
  clean report; fix the cause or record an explicit, explained exclusion.

## Claude Code notes

- Do not use Claude Code's memory system for project facts. Write them here or in `docs/`, where
  they are versioned and visible to everyone.
- Record lessons in "Lessons learned" below when a tool or convention behaved in a non-obvious way
  or the owner corrected an approach. Criterion: would the next agent, starting cold, repeat it?
- One canonical place per fact. Link instead of copying.
- Every rating used in a design decision (voltage, current, temperature, surge) is read from the
  part's datasheet and cited with document and page or table. A number from memory is unverified.
- Describe changes with past tense for the old behaviour and present tense for the new.

### Lessons learned

- **pcbnew (KiCad 10.0.1): never let Python free an item removed from a board.** After
  `board.Remove(item)` and the item's garbage collection, pcbnew returns untyped `SwigPyObject`
  pointers for the rest of the process (`AttributeError: 'SwigPyObject' object has no attribute …`).
  Keep removed items referenced until exit, as `tools/kilayout.py` `clear()` does. For the same
  reason look footprints up in a dict built from `GetFootprints()`, not with
  `FindFootprintByReference()`.
- **Freerouting: use the jar, not the native `freerouting-cli`.** The 2.5.0 native macOS build
  throws a serialization error on the first routing pass and then hangs forever.
- **`konnect` without arguments on a terminal is an installer.** It writes skills and hooks into
  `~/.claude`. It is an MCP server only when started over a pipe by an MCP client.
- **easyeda2kicad output is not usable as fetched.** Always go through `scripts/fetch-lcsc.sh`
  (format upgrade, embedded 3D model, offset fix, no absolute paths), then check pin types and
  footprint against the datasheet.
- **A zero-violation report is only worth something if the check can fail.** `make selftest` proves
  it for the collision check. When adding a check, add the case that makes it fail.
