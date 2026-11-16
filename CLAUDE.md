# CLAUDE.md

Guidance for Claude Code (and any other agent or contributor) working in this repository.

## Project overview

Garden irrigation hardware: two custom boards and their 3D-printed enclosures.

- **Valve node:** sits in a valve box in the ground, switches 24 VAC solenoid valves, talks
  Modbus RTU over RS485 on a buried cable.
- **Controller:** sits in a dry shed, powers the bus, bridges it to Home Assistant via ESPHome.

The valve node's firmware (ATtiny1616, C++ on avr-libc without a framework) is in
`firmware/valve-node/`.

Boards are written as code (Zener), generated into KiCad 10 files, placed and routed by script, and
fabricated and assembled by JLCPCB. Enclosures are modelled in build123d. An agent does all of it
in files; the owner reviews each board at three hold points (specification, schematic, layout and
enclosure) and places every order himself.

**Status:** toolchain proven on a throwaway board. The valve node has a signed-off specification
([`docs/valve-node-spec.md`](docs/valve-node-spec.md)), a signed-off schematic with bill of
materials ([`docs/valve-node-schematic.md`](docs/valve-node-schematic.md)), an enclosure model
([`docs/valve-node-enclosure.md`](docs/valve-node-enclosure.md)) and a layout with fabrication
data ([`docs/valve-node-layout.md`](docs/valve-node-layout.md)). The owner signed off layout and
fabrication data, the third hold point, on 2026-11-15. The same day the owner moved termination
and bias of the bus to the controller, dropped the A/B swap jumpers and had the UPDI header
populated, so that nothing on the node is soldered by hand. That changed schematic and layout;
the owner signed both off again on 2026-11-16. The owner made a first test print of the enclosure on 2026-11-16; supports under the
board and two changes for printing followed from it. The same day a check before the order
(stock, a Codex review) replaced the status LED, the address switch and the valve fuse by
equivalents and fixed the placement file ([`docs/valve-node-layout.md`](docs/valve-node-layout.md),
"Check before the order"). The owner did the test fit with a paper print of the board the same
day: it fits. Nothing is ordered yet; the order is the owner's. The whole chain runs for
both boards (`make all BOARD=valve-node`, about two minutes). The valve node's firmware is written
and tested against a simulated bus ([`docs/valve-node-firmware.md`](docs/valve-node-firmware.md));
it has not run on a chip. No real board exists yet.

## Rules that are not negotiable

- **English only.** Everything that stays in the repository is English: docs, code, comments,
  commit messages, file names, schematic and board annotations. The project may be published.
- **No private data.** No IP addresses, Wi-Fi names, credentials, document IDs, personal names,
  home directory paths or garden layout beyond what the design needs. Firmware secrets go through
  ESPHome `!secret` and stay out of git. Before committing, run
  `git grep -n -I -e '/Users/' -e '192\.168' -e '@gmail'` and expect no hit except this line.
- **Only the owner orders.** Never upload to or order from JLCPCB or any shop.
- **Print, don't buy.** Mechanical parts (enclosures, seals, inserts, holders) are 3D-printed by the
  owner in TPU or PETG wherever practical. Buy one only when printing cannot do the job.
- **JLCPCB assembles every part.** Boards arrive fully assembled. Choose every electronic part from
  the JLCPCB/LCSC catalogue, by function and rating, from any manufacturer rather than a specific
  brand. Never plan a part the owner buys or solders himself.
- **Every polarised part shows its orientation.** ICs, optocouplers, diodes and connectors carry a
  pin 1 or polarity mark on the silkscreen, so the owner can check each part's rotation in
  JLCPCB's assembly preview (the parts to check: `docs/valve-node-layout.md`, "What the files
  cannot guarantee").
- **Every connector is shown in use.** For each connector, the enclosure and the layout show where
  its cable enters, that the cable has room to bend from the entry to the plug, and that the plug
  can be pulled out with the board installed.
- **Hold points.** A board's next stage does not start before the owner signed off the previous
  one. Each hold point shows the reasoning, not just the result; the hard part of this project is
  switching 24 VAC and surviving surges on a long buried cable, not routing.
- **Do not edit generated files by hand.** `boards/*/eda/` is written by `make apply`,
  `make arrange`, `make layout` and `make drc`. Change the `.zen` source, `schematic.py`,
  `layout.py` or `mech.json` instead.

## Commands

```bash
make setup                 # once per checkout: pinned tools into .tools/, Python env into .venv/
make all BOARD=<board>     # whole chain: source -> KiCad files -> ERC -> layout -> DRC -> fab -> enclosure -> collision
make verify BOARD=<board>  # all checks, no committed file is modified
make help                  # every target with its output
make firmware-test         # valve node firmware: unit tests and bus test against the simulator
```

One target per output; the table is in [`docs/toolchain.md`](docs/toolchain.md). `BOARD` defaults
to `throwaway`, the smoke-test board: after changing a tool version or anything in `tools/`, run
`make all && make selftest` on it before touching a real board. `make selftest` also runs checks
on the valve node's committed files; after changing its layout, run `make all BOARD=valve-node`
first.

## Layout

| Path | Content |
|---|---|
| `boards/<board>/<board>.zen` | Schematic source (Zener) |
| `boards/<board>/schematic.py` | Schematic arrangement script (plain Python, `tools/schlayout.py`); optional |
| `boards/<board>/mech.json` | Board outline and mounting holes: the one interface between board and enclosure |
| `boards/<board>/layout.py` | Placement, design rules and routing (runs in KiCad's Python via `tools/kipython`) |
| `boards/<board>/classmap.json` | Colours for the copper-by-net-class picture of `make plots`; optional |
| `boards/<board>/enclosure.py` | Enclosure model (build123d, runs in the project venv via `uv run`) |
| `firmware/valve-node/` | Valve node firmware: logic in `core/`, chip-specific code in `src/`, simulator in `sim/`, tests |
| `boards/<board>/eda/` | Generated KiCad project, committed so the design opens without the toolchain |
| `lib/` | Shared parts: copied KiCad symbols and footprints, LCSC footprints, JLCPCB design rules, part-number mapping ([`lib/README.md`](lib/README.md)) |
| `tools/` | Shared scripts: layout helpers, grid router, fabrication outputs, collision check, self-tests, printable thread, renderer for enclosure pictures |
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
| What does the valve node's schematic add to the specification, what was checked, what goes to the layout? | [`docs/valve-node-schematic.md`](docs/valve-node-schematic.md) |
| What does the valve node's enclosure look like, how does it seal, where do outline and connector positions come from? | [`docs/valve-node-enclosure.md`](docs/valve-node-enclosure.md) |
| Where do the valve node's parts sit, how is 24 VAC kept from the logic, what does an order cost, how is the fit tried? | [`docs/valve-node-layout.md`](docs/valve-node-layout.md) |
| What does the valve node do on the bus, which registers are new, how is the firmware built, tested and programmed? | [`docs/valve-node-firmware.md`](docs/valve-node-firmware.md) |
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
- Net classes and custom design rules of a board are written by its `layout.py`
  (`kilayout.write_rules`) into `eda/<board>.kicad_pro` and `eda/<board>.kicad_dru`. `pcb apply`
  keeps them but resets the `Default` class from `lib/jlcpcb.zen`.
- Two routers. The throwaway board is routed by Freerouting (`Layout.autoroute`), the valve node
  by coordinates plus `tools/gridroute.py` (`Layout.router`). Why: `docs/toolchain.md`,
  "Routing".
- Firmware logic lives in `firmware/valve-node/core/` and has no hardware access, so it
  runs in the simulator and the tests unchanged. Anything that touches a pin or a peripheral goes
  into `src/main.cpp`. After a firmware change run `make firmware firmware-test`.
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
- **Zener joins pins that share a name into one net.** KiCad's optotriac symbol calls both unused
  pins `NC`; the board netlist tied pin 3 to pin 5 (the substrate). Give such pins distinct names
  when copying the symbol (`scripts/copy-kicad.py`), and read `eda/default.net` for nets named
  `NC_…` with more than one node.
- **Zener's generated schematic is a netlist, not a drawing.** A board that a person has to review
  needs a `schematic.py`. Zener's in-place update of an arranged schematic reformats it and broke
  it once (library symbol renamed, instances dangling), so `make apply` deletes the schematic,
  recreates it and reruns the arrangement; never commit a schematic that `make apply` did not
  finish.
- **A zero-violation report is only worth something if the check can fail.** `make selftest` proves
  it for the collision check. When adding a check, add the case that makes it fail.
- **OpenCascade (build123d 0.13) and threads.** A ridge swept along a helix and fused to a
  cylinder gave an invalid solid with a wrong volume. `tools/printthread.py` lofts through
  cross-sections instead, which is valid. Intersecting two such thread solids with each other
  still returns nonsense (zero, or the whole volume); against plain bodies it is correct. Check a
  boolean's volume against a hand estimate whenever a thread is involved.
- **A fetched 3D model can sit turned on a correct footprint.** The valve terminal block's pads
  matched the manufacturer's drawing; its model stood turned by 180° and 2.8 mm off (offset and
  rotation as `scripts/fetch-lcsc.sh` left them). The collision check passed with it. After
  fetching a part, compare the model's outline in the board STEP with the drawing and look at a
  render: which way does the opening face?
- **A connector is not finished without its mating half.** The valve node's pluggable screw
  terminals fitted; their plugs did not, and could not be pulled with the board in place. Model
  the mated plug and the travel it needs to come free, and put it into the collision check
  (`plugs.step` of `boards/valve-node/enclosure.py`). A wire is a mating half too: a triac of
  2.3 mm stood 1.4 mm in front of a terminal block's wire opening that begins 1.4 mm above the
  board. DRC and the collision check passed; the render showed it. Keep the approach to a wire
  opening free of parts higher than its lower edge.
- **JLCPCB's parts catalogue is the source for stock and price.** The community mirror
  (jlcsearch) missed parts that were in stock and returns at most 100 rows per query. The public
  part pages (`jlcpcb.com/partdetail/C…`) and the catalogue search show stock, price, assembly
  type and the datasheet.
- **Zener does not refresh a footprint that is already on the board.** After changing a file in
  `lib/` (pads of the bus jack), `make apply` reported "layout updated" and the board kept the
  old pads. Delete `eda/<board>.kicad_pcb` and `eda/snapshot.layout.json`, then
  `make apply layout`: the layout script rebuilds everything else.
- **KiCad 10.0.1 did not report a track inside a rule area that forbids tracks.** Zones stay out
  of such an area, a track drawn through it passed DRC. A keep-out that has to hold is also a
  `disallow` rule in the board's `.kicad_dru`, and `make selftest` draws a track into it
  (`tools/selftest-drc.py`). Found only because the self-test was written.
- **Freerouting 2.5.0 does not finish a board with a 0.4 mm pitch package.** On the valve node it
  left 8 to 13 connections open in every run and wrote tracks of 0.12 mm. More passes, narrower
  tracks and pre-drawn stubs did not help. `tools/gridroute.py` replaced it there.
- **Two identical connectors side by side cannot be passed through without crossings.** Each wire
  crosses every other one once. Decide per wire on which side of the pins and on which layer it
  runs before placing anything (`docs/valve-node-layout.md`, "The pass-through").
- **A printed part is designed for the way it lies on the bed.** The first test print of the valve
  node's base needed support under the threads of the cable entries and inside their bores; it
  could only be broken out, and took the thread with it. Look at every face that overhangs more
  than 45° in the print orientation: give a thread on its side a flat underside for the support,
  and a hole on its side a flat roof between 45° flanks (`teardrop` in
  `boards/valve-node/enclosure.py`). A part pressed on from above (a connector, a button) needs
  something under the board, not only the screws in its corners.
- **No PlatformIO or Arduino core for AVR firmware.** PlatformIO's AVR compiler (GCC 7.3 from
  2022) and its avrdude are Intel binaries and do not run on Apple silicon without Rosetta;
  megaTinyCore ships the same compiler. The firmware is built with Homebrew's native avr-gcc 14
  and avrdude from a plain Makefile (owner's decision, 2026-11-14).
- **JLCPCB places a part by its own footprint, not by ours.** Turn and shift in the placement
  file are corrections between the two. Fetch JLCPCB's footprint with
  `uvx easyeda2kicad@1.0.1 --footprint --lcsc_id=C… --output <scratch dir>` and fit it onto ours
  pad by pad: on the valve node that gave the turn of all nine parts the preview showed, and the
  shift of one within 0.03 mm. It also covers parts the preview shows without a model. Pad
  numbers of two-pin parts (LED) can differ in meaning; check those by the polarity mark.
- **Never retype pad positions; read them from the footprint.** The pockets under the RJ45 jacks
  came from a hand-typed list with the two rows of the contacts' zigzag swapped. Neighbouring
  pockets overlap into one slot, so the collision check passed; the owner saw it on the print.
  `footprint_pads` in `boards/valve-node/enclosure.py` reads them from `lib/lcsc/`.
- **No renderer is installed for build123d.** Pictures of an enclosure come from
  `tools/render3d.py` (numpy and Pillow, both already there). build123d's own `tessellate()`
  stops at a face the mesher left empty; the renderer meshes through OCP and skips it.
