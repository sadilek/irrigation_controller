# Valve node: schematic and bill of materials

The second of three hold points for the valve node. The layout does not start before the owner
signed this page off, together with the schematic PDF and the bill of materials.

Status: signed off by the owner on 2026-11-14. The layout that follows it is described in
[`valve-node-layout.md`](valve-node-layout.md); it left the schematic as it is. Changed
after sign-off, by the owner's decision: the moisture sensor input is gone (deviation 5).

The circuit and the reason for every part are in [`valve-node-spec.md`](valve-node-spec.md). This
page says what the schematic adds to it, where it deviates, what was checked and what is handed
to the layout.

## What to review

| Output | Command | File |
|---|---|---|
| Schematic, one A3 sheet | `make schematic BOARD=valve-node` | `build/valve-node/valve-node-schematic.pdf` |
| Bill of materials, populated and unpopulated footprints | `make bom BOARD=valve-node` | `build/valve-node/valve-node-bom.csv`, `.md` |
| Electrical rules check | `make erc BOARD=valve-node` | `build/valve-node/erc.rpt` |

Sources: [`valve-node.zen`](../boards/valve-node/valve-node.zen) (board),
[`output.zen`](../boards/valve-node/output.zen) (one valve output, instantiated twice) and
[`schematic.py`](../boards/valve-node/schematic.py) (where each symbol sits on the sheet).

The PDF carries values, not part numbers. Review it next to the bill of materials.

## Checks

| Check | Result |
|---|---|
| Zener compile: connectivity, typed nets, capacitor voltages against rail voltages | passes |
| KiCad ERC, with the two rules disabled that [`toolchain.md`](toolchain.md) explains | 0 violations |
| Drawing against source: after arranging, Zener compares the schematic's netlist with the source and any difference stops the build | no difference |
| `make selftest`: one net label is renamed and the comparison has to fail | fails as expected |
| Every populated part has a row in `lib/jlcpcb-parts.csv` | 26 lines, 39 parts |
| Run twice, `make apply` writes the same schematic byte for byte | yes |
| Pin assignment of every part with more than two pins against its datasheet | all confirmed, see [below](#checked-against-datasheets) |

## Population options

A part crossed out in the schematic is a footprint without a part. The bill of materials lists
these footprints with "Populated: no".

| Option | Standard board | To use it |
|---|---|---|
| Outputs 3 and 4 | Not on this board (owner, 2026-11-14): the footprints would cost board area on every node. A box with more valves gets a board variant of its own; `OUTPUTS` in `valve-node.zen` is the one line that changes | |
| Current sensing | Not on the board. The specification replaced it by the output monitor, which is populated on every output | |
| Termination | R14 not populated, jumper JP5 open | Populate 120 Ω and bridge JP5 |
| Bias | R11 and R12 not populated | Populate 1 kΩ each on one node, if the idle voltage measured at commissioning is between 40 and 200 mV |
| A/B swap | JP1 and JP2 bridged 1-2 in copper: brown is A | Cut both bridges, solder 2-3 on both |
| Spare pair parallel to 24 VAC | JP3 and JP4 open | Bridge both, on every node |
| Programming header | J3 not populated | Solder a 3-pin header or use spring pins: UPDI, 5 V, ground |

## Reference designators

Zener numbers the parts itself, so the references differ from the ones the specification used.

| Specification | Schematic | Part |
|---|---|---|
| U1 | U5 | Microcontroller |
| U2 | U7 | RS485 transceiver |
| U3 | U6 | 5 V regulator |
| Q1, Q2 | Q1, Q2 | Triacs |
| U4, U5 | U1, U3 | Optotriacs |
| U6, U7 | U2, U4 | Monitor optocouplers |
| D1 to D4 | D1 to D4 | TVS 12 V, series diode, RS485 TVS, TVS 24 VAC |
| F1, F2 | F1, F2 | Fuses 12 V and valves |
| J1, J2 | J1, J2 | Bus jacks IN and OUT |
| J3, J4 | J4, J5 | Valve plug headers |

## Deviations from the specification

Three points change the specification, all decided by the owner (2026-11-14): the board has two
outputs and no footprints for more, the regulator's output capacitor is a tantalum part (both at
this hold point), and the moisture sensor input is gone (after sign-off, with the enclosure).
Everything else is the specified circuit with the same parts, pins and values; the remaining
points are additions or choices the specification left open.

| # | Specification | Schematic | Reason |
|---|---|---|---|
| 0 | R3: two outputs populated, footprints for four | Two outputs, no further footprints. Pins PA3, PB1, PB4 and PB5 are unused and end on test pads (PA1 too since deviation 5) | Owner: the footprints take board area on every node; a box with more valves gets its own board. The ATtiny1616 stays: two outputs still need 12 pins, the ATtiny1614 has 11 |
| 1 | Regulator with a 10 µF input capacitor; R11: no electrolytic capacitors | A 10 µF, 16 V tantalum capacitor at the output (C1, TAJA106K016RNJ, case A) | The Holtek application circuit shows 10 µF at input and output, drawn as polarised parts, and says nothing about ceramics or ESR (HT75xx-1 Rev. 2.80, p. 13). A tantalum part is what it draws, so stability does not have to be proven on the first board. R11 is about wet electrolytics that dry out; a solid tantalum does not, and it is rated −55 to 125 °C with 3 Ω ESR (JLCPCB listing, not read from the datasheet). At 5 V it runs at a third of its voltage rating, behind a regulator that limits the current |
| 2 | "100 nF at the pin" for the microcontroller | Also 100 nF at the transceiver (C3) | TI asks for 100 nF close to VCC (SLLSF20B, p. 20) |
| 3 | Monitor pull-ups in the current budget | No resistors; the microcontroller's internal pull-ups | The pull-up is 20 to 50 kΩ (DS40002204A, I/O pin characteristics), at most 0.25 mA at 5 V, against at least 0.4 mA of collector current at the peak of each half-wave. The input goes low around every peak; the firmware samples for that. Four parts fewer |
| 4 | "Resistors in 0603 and 0805" | 0805 for the three resistors on the 24 VAC side of each output (gate 150 Ω, snubber 100 Ω, monitor 15 kΩ), 0603 elsewhere | 150 V working voltage and 125 mW instead of 75 V and 100 mW (UNI-ROYAL listing); the monitor resistor carries the full supply voltage |
| 5 | R13: optional input for a capacitive moisture sensor | No input: terminal, series resistor, capacitor and BAV99 clamp are gone, PA1 ends on a test pad like the other free pins. Until then the three protection parts were populated and the terminal was a footprint | Owner, 2026-11-14, after sign-off: the sensor on the installed system never worked properly, and the enclosure already has no cable entry for it ([`valve-node-enclosure.md`](valve-node-enclosure.md), deviation 3). Three populated parts fewer |
| 6 | Status LED, no value | 1 kΩ in series, about 2 mA | Forward voltage about 2.85 V at 2 mA (Everlight DSE-0006617 Rev. 2, p. 5, read from the curve). The LED's allowed current falls to 3 to 4 mA at 85 °C |
| 7 | Bias footprints, no value | 1 kΩ each | 5 V across 1 kΩ, 120 Ω, 1 kΩ gives 280 mV on a bus with one terminator |
| 8 | A/B swap by "a pair of solder jumpers" | Two three-pad jumpers, pads 1-2 joined in copper | The standard polarity needs no soldering on any board |
| 9 | Test pads on the four free pins | Five free pins with deviation 5, and three more pads: 5 V, ground, regulator input | Bring-up |
| 10 | Exposed pad of the microcontroller not mentioned | Connected to ground | Microchip recommends it (DS40002204A, p. 16) |
| 11 | Address switch and terminal blocks "not verified from a datasheet" | Verified | Switch: Kingtek drawing DSHP04TSGET-A, 25 mA at 24 V DC, −40 to 85 °C. Header: Cixi Kefa KF2EDGR-5.08, 300 V, 10 A, −40 to 105 °C |

## Bill of materials in short

26 lines, 39 parts, all on the top side. 11 lines are JLCPCB basic parts, 15 are extended parts
with a set-up fee per type. The two bus jacks and the two
valve headers are through-hole parts; everything else is surface-mount.

Not on the board and ordered loose: two plugs KF2EDGK-5.08-2P (C440880) per board.

JLCPCB solders the four through-hole parts, 20 joints per board (owner, 2026-11-15, with the cost
estimate of the layout hold point). They are marked `tht` in `lib/jlcpcb-parts.csv`, which puts
them into the JLCPCB BOM and placement file; `none` would leave them out.

Class and stock come from the specification's parts search of 2026-11-14 and a community mirror.
They are checked again on jlcpcb.com before the order, as are the placement rotations.

## Checked against datasheets

Pin assignment and footprint pad numbering of each part, read from the manufacturer's document.

| Part | Confirmed | Document |
|---|---|---|
| ATtiny1616-MNR | All 20 pins; TXD PB2, RXD PB3, XDIR PB0 | Microchip DS40001997C, p. 16 and 17 |
| THVD2410DR | 1 R, 2 /RE, 3 DE, 4 D, 5 GND, 6 A, 7 B, 8 VCC; A is high for a "1" | TI SLLSF20B, p. 3 and 13 |
| HT7550-1 | 1 GND, 2 VIN, 3 VOUT | Holtek HT75xx-1 Rev. 2.80, p. 5 |
| T410-600B-TR | A1, A2 on the centre lead and tab, G | ST DocID7699 Rev 9, p. 1 and 7 |
| EL3053S1(TA)-V | 1 anode, 2 cathode, 4 and 6 terminals, 3 open, 5 substrate, not connected | Everlight DPC-0000059 Rev. 12, p. 1 |
| LTV-814S-TA1 | 1 and 2 LED pair, 3 emitter, 4 collector | Lite-On LTV-8x4 Rev. J, p. 2 |
| PSM712-LF-T7 | 1 and 2 lines, 3 common; a line stands off +12 V and −7 V against pin 3 | ProTek 05094.R8, p. 1 |
| RJHSE-5080 | Pad 1 is contact 1; hole pattern within 0.02 mm | Amphenol modular jack catalogue, RJHSE-508X page; the single-part drawing could not be opened |
| DSHP04TSGET | Land pattern identical to the footprint; switch n joins pins n and 9 − n by geometry, the drawing has no pin numbers | Kingtek DSHP04TSGET-A |
| KF2EDGR-5.08-2P | Pitch, hole and outline | Cixi Kefa KF2EDGR-5.08 rev A |

One fault was found this way. Zener joins pins that share a name into one net, and KiCad's symbol
names both unused optotriac pins "NC". The board would have connected pin 3 to pin 5, the
substrate that must stay open. The pins now carry different names, and the lesson is in
`CLAUDE.md`.

## Handed to the layout

What the layout did with each point is in [`valve-node-layout.md`](valve-node-layout.md), "24 VAC
and logic" and "Deviations".

- Net classes and the 3 mm rule of the specification's "Layout rules" are not in the source yet.
  They are set when the layout starts, before routing.
- Footprints that differ from the manufacturer's land pattern and need a decision there: the
  fuses (KiCad's 1812 pattern is 5.40 mm long, the datasheet asks for 6.76 mm), the triac (KiCad's
  DPAK pattern is 10.6 mm long, ST's 12.7 mm), the bus jack (holes 1.0 mm against 0.89 mm, pegs
  3.3 mm against 3.25 mm).
- Bus jack: the plug opening is on the footprint's +y side, the latch stands 0.89 mm proud of the
  front face, the body is 13.2 mm high. Valve header: the plug enters from +y, the header is
  12.2 mm deep and 8.4 mm high.
- The tantalum capacitor is polarised: pad 1 is the positive terminal.
- Pins may be swapped among outputs, monitors and address switch if routing asks for it; the
  specification says which ones are fixed.
- The bus jack and the valve header footprints are fetched LCSC data, the point that
  [`license.md`](license.md) lists before publication.

## Open points

| Point | Needed for | Who, when |
|---|---|---|
| Tantalum capacitor C1: temperature range and ESR are from the listing | C1 | Read the Kyocera AVX TAJ datasheet before the order |
| Through-hole parts soldered by JLCPCB or by the owner | BOM | Decided on 2026-11-15: JLCPCB ([`valve-node-layout.md`](valve-node-layout.md), "Who solders the through-hole parts") |
| Fuse maker: the documents linked at LCSC are from another maker than the name in the listing, and the 0.2 A type is marked "UL pending" | Order | Before the order |
| The points listed in the specification's "Open points" | | unchanged |
