# Irrigation controller

Custom boards and 3D-printed enclosures for a garden irrigation system: a valve node that switches
24 VAC solenoid valves from an RS485/Modbus bus, and a controller that powers the bus and connects
it to Home Assistant.

Everything is source text: schematics in [Zener](https://github.com/diodeinc/pcb), generated into
KiCad 10 files, placed and routed by script, enclosures in [build123d](https://github.com/gumyr/build123d).

**Status:** the toolchain works end to end on a throwaway board. The real boards are not designed yet.

## Quick start

Requires macOS on Apple Silicon, KiCad 10 in `/Applications`, [`uv`](https://docs.astral.sh/uv/) and `make`.

```bash
make setup    # pinned tools into .tools/, nothing installed system-wide
make all      # throwaway board: schematic -> checks -> layout -> fabrication data -> enclosure -> collision check
make help     # one command per output
```

Outputs land in `build/throwaway/`. The generated KiCad project in `boards/throwaway/eda/` opens in
KiCad 10 without any of the tools above.

## Documentation

- [`docs/toolchain.md`](docs/toolchain.md): the chain, every command, tool choices, known weaknesses
- [`docs/bus-protocol.md`](docs/bus-protocol.md): cable, addresses, registers and timing of the RS485/Modbus bus
- [`docs/existing-system.md`](docs/existing-system.md): the installation being replaced, valve data, known weaknesses, open points
- [`lib/README.md`](lib/README.md): part libraries and the JLCPCB part mapping
- [`docs/license.md`](docs/license.md): which license covers what, and what must be settled before publishing
- [`CLAUDE.md`](CLAUDE.md): rules and conventions for agents and contributors

## License

Hardware: [CERN-OHL-P-2.0](LICENSES/CERN-OHL-P-2.0.txt). Software: [MIT](LICENSES/MIT.txt).
Documentation: [CC-BY-4.0](LICENSES/CC-BY-4.0.txt). Details and exceptions in [`docs/license.md`](docs/license.md).
