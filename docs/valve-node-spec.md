# Valve node: specification

What the valve node board has to do, how it is built and why. This is the first of three hold
points for the board. The schematic does not start before the owner signed this page off.

Status: signed off by the owner on 2026-11-14. The schematic that follows it is described in
[`valve-node-schematic.md`](valve-node-schematic.md); its "Deviations" list what changed after this
sign-off, in particular: two outputs without footprints for more, and a tantalum capacitor at the
regulator output. The enclosure is described in [`valve-node-enclosure.md`](valve-node-enclosure.md);
it changes "Outline and connectors" below: the board is 96 × 44 mm with all connectors on one long
edge, the jacks sit 34 mm apart, all cables enter through one wall, the moisture sensor has no
cable entry, and only the bus inserts are slit. After the sign-off the owner dropped the moisture
sensor input from the board altogether (2026-11-14, schematic deviation 5); R13, the pin
assignment and the current budget below say so, the outline section is superseded by the enclosure.

The node replaces every existing node on the buried cable. Cable, wiring, addresses and registers
stay as described in [`bus-protocol.md`](bus-protocol.md). The installation it goes into, with
its weaknesses and open points, is in [`existing-system.md`](existing-system.md).
[Answers to the existing system](#answers-to-the-existing-system) lists each of them with what
this board does about it.

Every rating below is read from the datasheet named in [Sources](#sources) and cited with page or
table. Stock, class and price are from the JLCPCB parts search on 2026-11-14 and have to be
checked again before an order.

## Decisions the owner is asked to make

Signing this page off accepts these six points. Each one is explained in the section named.

1. **ATtiny1616 instead of ATtiny1614** (accepted by the owner on 2026-11-14, VQFN package). Four outputs with one monitor input each, the address
   switch and the LED need 16 pins. The ATtiny1614 has 11.
   See [Microcontroller](#microcontroller-and-pin-assignment).
2. **The 24 VAC side is isolated from the logic.** Optocouplers drive the triacs. No 24 VAC wire
   connects to the 12 V ground. See [Valve outputs](#valve-outputs).
3. **Each output reports whether it works.** A second optocoupler per output replaces the "valve
   current sensing" of the baseline. It costs no voltage and also finds a broken wire before the
   valve is opened. See [Output monitor](#output-monitor).
4. **The node closes its valves on its own.** After 60 s without a valid request, after 120 min of
   run time, and when a second output of the same node is opened.
   See [Behaviour](#behaviour-input-for-the-firmware).
5. **Termination stays open on every node.** At 9600 baud the cable needs none, and each
   terminator costs supply current. See [RS485](#rs485).
6. **The bus connects through two RJ45 jacks, not screw terminals** (owner's proposal,
   2026-11-14). Both jacks sit on one short edge, the valve terminals on the opposite one. The
   cable entries are sealed with printed split inserts, so a crimped plug does not have to pass
   through the seal. See [Outline and connectors](#outline-and-connectors).

## Requirements

| # | Requirement | Source |
|---|---|---|
| R1 | Works on the existing cable with the existing controller: Modbus RTU, 9600 baud, 8N1, registers 0 to 4 unchanged | [`bus-protocol.md`](bus-protocol.md) |
| R2 | Switches Hunter PGV-101 solenoids on 24 VAC: 0.37 A at switch-on, 0.21 A holding, 50 Hz | [`existing-system.md`](existing-system.md#valves) |
| R3 | Two outputs populated, footprints for four | Baseline |
| R4 | One firmware for all nodes, address set on the board | Baseline |
| R5 | Powered from the 12 V pair, runs at the far end of 100 m of copper-clad aluminium cable with five other nodes | [`existing-system.md`](existing-system.md#cable) |
| R6 | Survives a reversed 12 V connection | Baseline |
| R7 | Survives induced surges on the buried cable without a part that wears out | Plan |
| R8 | Never holds the bus and never keeps a valve open when the controller is gone | [`existing-system.md`](existing-system.md#known-weaknesses) |
| R9 | Reports per output whether current can flow and whether the output conducts | [`existing-system.md`](existing-system.md#known-weaknesses), "No feedback" |
| R10 | A node with a fault does not take the 12 V supply or the 24 VAC supply down for the others | Bus fault of 2026-11 |
| R11 | Parts rated for −40 to +85 °C, no electrolytic capacitors | Valve box in the ground |
| R12 | Two layers, assembled by JLCPCB, bus passed through from one jack to the other | Baseline |
| R13 | One status LED. The baseline's optional input for a capacitive soil moisture sensor is dropped: the sensor on the installed system never worked properly (owner, 2026-11-14) | Baseline |

Not required, and not claimed: surviving a direct lightning strike, and surviving 24 VAC wired to
the 12 V or RS485 wires. A cable crimped to the standard colour order cannot be miswired at the
node, and a cable tester checks it. What remains is a bus cable plugged into network equipment,
which the 24 VAC would damage; the jacks are labelled.

## Block diagram

```
 bus jack IN                                                              bus jack OUT
 ┌──────────┐                                                             ┌──────────┐
 │ A        ├──────────────────────────┬──────────────────────────────────┤ A        │
 │ B        ├──────────────────────────┼─┬────────────────────────────────┤ B        │
 │ GND      ├───────────────┬──────────┼─┼────────────────────────────────┤ GND      │
 │ +12 V    ├──────┬────────┼──────────┼─┼────────────────────────────────┤ +12 V    │
 │ spare 1  ├──────┼────────┼──────────┼─┼────────────────────────────────┤ spare 1  │
 │ spare 2  ├──────┼────────┼──────────┼─┼────────────────────────────────┤ spare 2  │
 │ 24 VAC b ├──────┼────────┼──────────┼─┼───────────────┬────────────────┤ 24 VAC b │
 │ 24 VAC a ├──────┼────────┼──────────┼─┼────────┬──────┼────────────────┤ 24 VAC a │
 └──────────┘      │        │          │ │        │      │                └──────────┘
                 fuse F1    │      TVS D3 to GND  ├─TVS D4─┤
                   │        │          │ │        │      │
              TVS D1 to GND │      120 Ω behind  fuse F2  │
                   │        │      solder jumper  │      │
               diode D2     │          │ │        │      │
                   │        │    ┌─────┴─┴────┐   │      │
            ┌──────┴─────┐  │    │ RS485      │   │      │        isolation
            │ 5 V        │  │    │ transceiver│   │      │        barrier
            │ regulator  │  │    └─────┬──────┘   │      │           ║
            └──────┬─────┘  │   TXD RXD│XDIR      │      │           ║
                   │ 5 V    │    ┌─────┴──────┐   │   ┌──┴────────┐  ║
                   └────────┼────┤ ATtiny1616 ├───╫───┤ output 1  ├──╫── valve 1
   address switch ──────────┼────┤            ├───╫───┤ output 2  ├──╫── valve 2
   status LED ──────────────┼────┤            ├───╫───┤ (output 3)├──╫── (valve 3)
   UPDI header ─────────────┼────┤            ├───╫───┤ (output 4)├──╫── (valve 4)
                            │    │            │   ║   └──┬────────┘  ║
                            │    └────────────┘   ║      │
                           GND                    ║   valve common (fused 24 VAC a)

 one output:

   MCU pin ──220 Ω──▶ optotriac LED ║ optotriac ──150 Ω──┐
                                    ║                    │ gate
   MCU pin ◀── phototransistor      ║        ┌───────────┴──┐
               (AC optocoupler)     ║        │    triac     ├── A2 ── valve terminal
                     ▲              ║        └──────┬───────┘
                     ║              ║               A1 ── 24 VAC b
                     LED ◀─ 15 kΩ ── across A1 and A2, parallel to 100 Ω + 100 nF
```

Outputs in brackets are footprints without parts.

## Power supply from the 12 V pair

Path: jack, resettable fuse F1, bidirectional TVS D1 to ground, series diode D2, 10 µF
ceramic capacitor, regulator, 5 V.

| Part | Choice | What the datasheet says | Why |
|---|---|---|---|
| F1 | mSMD020-60V, 1812 | Holds 0.20 A at 25 °C and 0.14 A at 60 °C, trips at 0.40 A, 60 V, 0.35 to 5 Ω (Techfuse mSMD series, performance table and "Ihold versus temperature") | If D1 or anything behind it fails short, F1 takes this node off the 12 V pair and the others keep running (R10). A 1206 part with 0.10 A hold drops to 0.06 A at 60 °C, too close to the node's own current. |
| D1 | SMBJ15CA, bidirectional | Stand-off 15 V, breakdown from 16.7 V, clamps at 24.4 V with 24.6 A, 600 W for 10/1000 µs (Vishay 88392, p. 2) | Bidirectional, so a reversed supply does not short the bus through the TVS. 15 V leaves room above a 12 V supply that runs high. |
| D2 | M7, 1000 V 1 A | 1.1 V at 1 A (MDD M7, p. 1) | Reverse polarity protection (R6), and it keeps a negative surge clamped by D1 away from the regulator. A Schottky diode would save about 0.4 V that the budget does not need. |
| Regulator | HT7550-1, SOT-89 | Input up to 30 V, absolute maximum 33 V, at least 100 mA at 7 V input, 2.5 µA quiescent, −40 to 85 °C (Holtek HT75xx-1 Rev. 2.80, p. 4 and 8) | The 24.4 V clamp of D1 is below its 30 V operating limit. Linear on purpose: see below. |

A linear regulator and not a switching one. The node draws 8 to 25 mA; a buck converter would
halve that, but the supply current is already small against what the cable can carry, and a
converter adds an inductor, switching noise next to the bus and a part that can fail. The
regulator turns at most (12 V − 5 V) × 25 mA = 0.18 W into heat, against 0.50 W allowed for the
package (Holtek, p. 4).

The node works with at least 8.3 V at its jack: 7 V at the regulator, 1.1 V for D2 and 0.2 V
for F1 (5 Ω at 40 mA). Below that the 5 V rail may sag, the brown-out detector resets the
microcontroller at 4.2 V (Microchip DS40002204A, p. 510) and the valves close.

### Current budget on the 12 V pair

All 5 V current is 12 V current, because the regulator is linear.

| Consumer | Current | Source |
|---|---|---|
| Microcontroller, active at 5 MHz and 5 V | 3.2 mA typical | DS40002204A, table 36-4, p. 508 |
| RS485 transceiver, listening | 2.4 mA maximum | TI SLLSF20B, 6.7, p. 6 |
| Status LED, address switch, monitor pull-ups | 2 mA | by design |
| **Node idle** | **about 8 mA** | |
| One valve open: optotriac LED through 220 Ω | + 16 mA typical, 18 mA maximum | Everlight, forward voltage 1.18 V typical, p. 3 |
| Transmitting into one 120 Ω terminator | + about 35 mA for 8 to 16 ms per answer | TI SLLSF20B, 6.7: 4 V typical into 100 Ω |
| Transmitting into two terminators (60 Ω) | + about 58 mA | TI SLLSF20B, 6.7: 3.3 V typical into 60 Ω |

For the whole cable, with the 26 Ω loop resistance estimated in
[`existing-system.md`](existing-system.md#cable) for 100 m and every node assumed at the far end:

| Case | Current | Drop | Voltage at the far node |
|---|---|---|---|
| Today's four nodes, one valve open | 48 mA | 1.2 V | 10.8 V |
| The same while a node answers into one terminator | 83 mA | 2.2 V | 9.8 V |
| Six nodes, one valve open | 64 mA | 1.7 V | 10.3 V |
| Six nodes, one valve open, a node answering into two terminators | 122 mA | 3.2 V | 8.8 V |

The first three cases leave at least 1.5 V above the 8.3 V the node needs. The last case does not,
and it is the reason for decision 5: with termination open on the nodes, the fourth line becomes
99 mA and 9.4 V. The real cable is shorter than 100 m and the nodes are spread along it, so the
real drop is roughly half of each figure. The old nodes pulled the supply down to about 6 V with
one relay energised (owner's calculation).

## RS485

| Part | Choice | What the datasheet says |
|---|---|---|
| Transceiver | THVD2410DR, SOIC-8, at 5 V | Bus pins withstand ±70 V, receiver works over ±25 V common mode, 1/8 unit load, fail-safe receiver, thermal shutdown, driver enable with internal pull-down (TI SLLSF20B, p. 1, 3 and 4) |
| TVS | PSM712-LF-T7, SOT-23, at the jacks | Stand-off 7 V and 12 V, clamps at 30 V with 30 A and at 17 V with 34 A, 600 W for 8/20 µs (ProTek 05094.R8, p. 2) |
| Termination | 120 Ω behind a solder jumper, open | |
| Bias | Two resistor footprints, A to 5 V and B to ground, empty | |

Why this transceiver and not a standard one. The TVS limits a surge to 30 V. A standard
transceiver allows about 14 V on its bus pins, so the remaining 16 V would have to be absorbed by
series resistors and the transceiver's own protection. The THVD2410 withstands 70 V, so the TVS
alone protects it with a margin of 40 V and no series resistors are needed. TI states the same
rule: series resistors are needed only if the TVS clamps above what the bus pins allow (SLLSF20B,
11.1, p. 21). The baseline named the SM712; the PSM712 is the same part from another maker and a
JLCPCB basic part.

Direction control. The microcontroller's USART drives the driver enable pin itself, high while a
frame is sent and low when it ends (DS40002204A, 24.3.3.2.6, "RS-485 Mode", p. 327). The pin has a
10 kΩ pull-down, so the driver is off during reset, programming and a firmware crash. The receiver
enable is tied to the same pin, so the node does not hear its own answer.

Termination. One bit at 9600 baud lasts 104 µs. A reflection on 100 m of cable has died out after
a few microseconds, long before the receiver samples the bit, so the cable works without
termination. Each terminator costs about 30 mA while a node transmits. All node jumpers stay open.
The existing controller module, which stays for now, probably carries a fixed 120 Ω; that does no
harm.

Idle level. The existing controller module drives only one level and leaves the other to its bias
resistors. The new receiver reads an idle bus as "1" when the voltage between A and B is above
200 mV or within ±40 mV (SLLSF20B, 6.7, p. 6); between 40 and 200 mV the datasheet promises
nothing. Measured once at commissioning, with the first new node connected: if the idle voltage is
in that gap, the two bias footprints on one node are populated.

Polarity. The brown wire goes to the transceiver's pin A, which is the more positive wire on an
idle bus. If the letters on the existing module mean the opposite, a pair of solder jumpers next
to the transceiver swaps A and B. A crimped plug cannot be rewired, so the swap is on the board.

## Valve outputs

One output consists of a triac, an optotriac that fires it, a snubber and the
[monitor](#output-monitor).

| Part | Choice | What the datasheet says |
|---|---|---|
| Triac | T410-600B-TR, DPAK | 600 V, 4 A, surge 30 A for 20 ms, gate trigger current 10 mA maximum, three quadrants, commutates 2.0 A/ms at 10 V/µs without snubber, on-state at most 0.89 V + 0.12 Ω × I, 70 K/W on 0.5 cm² copper (ST DocID7699 Rev 9, tables 3 to 6, p. 2 and 3) |
| Optotriac | EL3053S1(TA)-V, random phase | Fires with 5 mA LED current, 600 V, 1 A peak, on-state at most 2.5 V, withstands 1000 V/µs, isolation 5000 V RMS (Everlight DPC-0000059 Rev. 12, p. 2 to 4) |
| Gate resistor | 150 Ω between triac A2 and the optotriac | |
| Gate to A1 | 1 kΩ | |
| Snubber | 100 Ω in series with 100 nF, 100 V, across the triac | |

Why a triac and not a relay or a MOSFET relay.

- A triac switches off by itself when the current passes zero. A solenoid stores energy while
  current flows; a relay contact or a MOSFET relay interrupts the current at any moment and has to
  absorb that energy, a triac never has to.
- It needs no coil current. One energised relay was the largest load on the 12 V pair.
- A 600 V part on a 34 V peak supply has a margin that a 60 V MOSFET relay does not have. The TVS
  on the 24 VAC pair clamps at 77 V, which is above a 60 V part's rating and far below 600 V.
- The price is about 1 V of drop across the triac (0.89 V + 0.12 Ω × 0.52 A at switch-on). A relay
  contact drops nothing. The valve at the far end sees less than 24 V already
  ([`existing-system.md`](existing-system.md#cable)), and the minimum voltage at which a PGV-101
  pulls in is not known. This is the main risk of the design and it is tested on the first board
  before anything else: one node, the longest cable run, the farthest valve.

Why this triac.

- Current. 0.21 A holding heats the triac with 0.17 W, a rise of 12 K. With a shorted valve wire
  the fuse lets up to 1 A pass until it trips; that is 0.9 W and a rise of 64 K, which a 4 A part
  in a DPAK package survives. A 1 A part in a small package would not.
- Commutation. When the current of an inductive load passes zero, the voltage across the triac
  jumps to the supply's momentary value, and a triac can fire again by mistake. The stress is the
  current's slope at the zero crossing: 2π × 50 Hz × √2 × 0.37 A = 0.16 A/ms at switch-on current.
  The triac is specified for 2.0 A/ms, twelve times more.
- Three quadrants. The optotriac circuit fires the triac only in the two quadrants where gate and
  load current have the same sign. Three-quadrant triacs are the type built for inductive loads.

Why a random-phase optotriac and not a zero-crossing one. A zero-crossing type fires only while
the voltage across it is close to zero. With a solenoid the current passes zero when the voltage
is near its peak, and at that moment the triac needs to be fired again. A zero-crossing type would
refuse.

Gate circuit. The triac fires once the supply's momentary voltage exceeds about 5 V: 1.3 V gate
voltage, up to 2.5 V across the optotriac, and 10 mA through 150 Ω. At the 77 V clamp level the
gate resistor limits the optotriac's current to 0.5 A, half its 1 A rating. The LED gets 16 mA
typical and at least 11 mA through 220 Ω from a pin that delivers 4 V at 15 mA (DS40002204A,
36.10, p. 513), more than twice the 5 mA the optotriac needs.

Snubber. The commutation figures say the triac does not need one. It is populated anyway: it
limits how fast the voltage rises across triac and optotriac when a surge arrives, and it costs
two passive parts. With the triac off it passes 0.75 mA through the solenoid.

Reset state. A microcontroller pin is an input after reset, so no LED current flows and every
valve is closed until the firmware opens it.

### Isolation between 24 VAC and logic

The 24 VAC pair and the 12 V pair have no connection on the board. The baseline did not say how
the triacs are driven; the simplest circuit ties one 24 VAC wire to ground and drives the gates
from the microcontroller. This design does not do that, for three reasons.

- A tie at every node would put the 24 VAC return wire and the 12 V ground wire in parallel. Valve
  current would then flow in the ground wire and shift each node's ground against the
  controller's, at 50 Hz, on the wire the bus refers to.
- A surge between the two pairs would enter the logic directly. With the barrier, the logic side
  sees only what couples through two optocouplers rated for 5000 V.
- A fault on the 24 VAC side, such as water in a valve connector, cannot reach the bus.

### Output monitor

An AC optocoupler with a 15 kΩ series resistor sits across each triac.

| Part | Choice | What the datasheet says |
|---|---|---|
| AC optocoupler | LTV-814S-TA1 | Two LEDs back to back, current transfer at least 20 % at 1 mA, isolation 5000 V RMS, −50 to 110 °C (Lite-On LTV-8x4 series Rev. J, p. 2, 9 and 10) |

When the triac is off, the full supply voltage lies across it and about 2 mA peak flows through
the monitor LED, the 24 VAC supply and the solenoid. When the triac conducts, the voltage across
it is about 1 V and the LED is dark. The firmware reads four cases.

| Output | Monitor sees voltage | Meaning |
|---|---|---|
| off | yes | 24 VAC present, wire and solenoid intact |
| off | no | 24 VAC missing, fuse tripped, wire or solenoid open, or triac shorted |
| on | no | triac conducts |
| on | yes | triac did not fire |

Why this and not a current measurement. Measuring current across the isolation barrier needs a
series element that drops 1.5 to 2 V, on a supply where every volt at the far valve counts. The
monitor drops nothing and reports a broken wire before the valve is asked to open. It cannot tell
a shorted solenoid from a good one; the fuse F2 covers that case.

Off-state current. Monitor and snubber together pass about 2 mA through a closed valve's solenoid,
1 % of the holding current. Hunter publishes no release current, so the first board is checked for
it: a valve has to close with the output off.

## Protection concept

### What the cable does to the node

The node sits in a plastic box in the ground and has no earth connection. A nearby lightning
strike or a switching event induces a voltage into the whole cable against earth. All eight wires
rise together, the node rises with them, and almost nothing flows through it. What the node sees
are the differences: between the two wires of a pair, and between one pair and another, because
the pairs end in different circuits at the controller. The protection therefore clamps each pair
where it enters the board and isolates the one pair that has no reason to share a ground with the
others.

| Path | Protection | Clamp level | Weakest part behind it |
|---|---|---|---|
| A or B against ground | PSM712 at the jacks | 30 V at 30 A | Transceiver bus pins, 70 V |
| +12 V against ground | SMBJ15CA behind fuse F1 | 24.4 V at 24.6 A | Regulator input, 30 V |
| 24 VAC a against b | SMBJ48CA at the jacks | 77.4 V at 7.8 A | Snubber capacitor, 100 V; triac and optotriac, 600 V |
| 24 VAC pair against logic | No clamp. Isolation by two optocouplers per output and board clearance | | Optocouplers, 5000 V RMS for one minute |
| Valve terminals | Behind the 24 VAC clamp; wires stay inside the box | | Triac, 600 V |

The 24 VAC TVS (Littelfuse SMBJ series, p. 2) has a stand-off of 48 V. That is the peak of
33.9 V RMS, enough for a transformer that runs 40 % above its 24 V rating without load. The
transformer's open-circuit voltage is not known; if a measurement shows more than 33 V, the next
size up is fitted.

A TVS does not age with each surge the way a varistor does. When a TVS is overloaded it fails
short. On the 12 V input the fuse F1 then removes the node from the supply. On the RS485 pair and
the 24 VAC pair a shorted TVS takes the pair down for every node. The fault is then found by
pulling the OUT plug box by box. A faulty node is taken out and its two cables are joined with
an RJ45 coupler, so the other nodes keep running.

What this does not cover: a direct or very close strike. The pairs inside one cable are insulated
from each other for some hundred volts at most. Where the cable itself breaks down, no part on the
board helps.

### Faults on the 24 VAC side

Fuse F2 (mSMD050-60V) sits between the 24 VAC pair and the valve commons of this node. It holds
0.50 A at 25 °C and 0.35 A at 60 °C, and trips at 1.0 A (Techfuse mSMD series). One valve holds at
0.21 A; the 0.37 A at switch-on last too short to trip it. A shorted solenoid or valve wire trips
F2 and leaves the 24 VAC pair up for the other nodes (R10).

One requirement goes to the controller specification. The 24 VAC supply must not be able to
deliver more than the triac's surge rating into a short at a node. The triac withstands 30 A for
one mains cycle, and F2 needs 0.15 s at 8 A. The present 8 VA transformer cannot come close. A
larger replacement gets a fuse at the controller.

### A node that hangs

- The driver enable pin is under hardware control and pulled low. A crashed firmware cannot hold
  the bus.
- The watchdog is switched on by a fuse. The firmware then cannot switch it off (DS40002204A,
  19.3.1, p. 170). A hung node resets, and a reset closes the valves.
- The transceiver switches its driver off above 150 °C (SLLSF20B, 6.7, p. 6).
- The brown-out detector resets the node when 5 V sags.

### Moisture

The enclosure keeps water out; that is the enclosure's job and its own test. On the board, the
24 VAC side and the logic side keep 3 mm distance (see [Layout rules](#layout-rules)). Proposal:
the owner sprays the assembled boards with conformal coating, with jacks, plugs, address switch
and UPDI header masked. JLCPCB's standard assembly does not include it.

## Microcontroller and pin assignment

ATtiny1616-MNR in a 3 × 3 mm VQFN-20, running at 5 V from the internal oscillator at 5 MHz.

Why not the ATtiny1614 of the baseline. The functions need 16 pins:

| Function | Pins |
|---|---|
| RS485: TXD, RXD, driver enable | 3 |
| Triac outputs | 4 |
| Output monitors | 4 |
| Address switch | 4 |
| Status LED | 1 |
| **Total** | **16** |

The ATtiny1614 has 11 usable pins, the ATtiny1616 has 17 (DS40002204A, table 5-1, p. 18). Both
are the same chip family with the same core, peripherals, memory and tools; the firmware does not
change. The alternative that keeps the ATtiny1614 is a board with two outputs and no footprints
for more; a box with a third valve would then get a second node. The VQFN version is chosen
because JLCPCB has 10,257 of it at $1.25, against 335 of the SOIC-20 at $2.34 and 815 of the
ATtiny1614 at $1.98. A VQFN cannot be reworked with a soldering iron; a defective one means hot
air or a new board.

Why this family at all, compared with the existing ATtiny85:

- A hardware USART replaces software serial. The oscillator is within ±2 % of its factory-measured
  frequency from 0 to 70 °C at 5 V (DS40002204A, table 36-12, p. 511), and each chip stores its
  own measured error so the baud rate generator can correct for it. A UART tolerates about ±4 %
  between two stations.
- The USART switches the transceiver's direction itself.
- EEPROM, watchdog and brown-out detector are built in. Programming needs one pin (UPDI).

| Pin | VQFN-20 | Function | Note |
|---|---|---|---|
| PA0 | 19 | UPDI | Programming header |
| PA1 | 20 | Free | Test pad |
| PA2 | 1 | Status LED | |
| PA3 | 2 | Monitor 4 | Free on a two-valve board |
| PA4 | 5 | Output 1 | High opens the valve |
| PA5 | 6 | Monitor 1 | Low while voltage lies across the triac |
| PA6 | 7 | Output 2 | |
| PA7 | 8 | Monitor 2 | |
| PB0 | 14 | Driver enable (XDIR) | Fixed by the USART; 10 kΩ pull-down |
| PB1 | 13 | Output 4 | Free on a two-valve board |
| PB2 | 12 | TXD | Fixed by the USART |
| PB3 | 11 | RXD | Fixed by the USART; internal pull-up |
| PB4 | 10 | Monitor 3 | Free on a two-valve board |
| PB5 | 9 | Output 3 | Free on a two-valve board |
| PC0 to PC3 | 15 to 18 | Address switch 1 to 4 | Switch to ground, internal pull-ups |
| VDD, GND | 4, 3 | 5 V | 100 nF at the pin |

With four outputs populated PA1 is the one pin left. On the standard two-valve board the five free
pins go to test pads. The layout may swap pins among outputs, monitors and switch if routing asks
for it. TXD, RXD and XDIR are fixed.

Address switch: four positions, binary, addresses 1 to 15. Position 0 is not a valid address
(broadcast); the firmware specification says what a node does with it. The switch is read at
start-up.

Programming: a three-pin header with UPDI, 5 V and ground. JLCPCB does not program the chip; the
owner does, once per board, with a serial UPDI adapter.

## Behaviour (input for the firmware)

The firmware has its own specification later. These points are fixed here because they are the
answer to weaknesses of the existing system and because the hardware is sized for them.

| Behaviour | Value | Reason |
|---|---|---|
| Registers 0 to 4 | As in [`bus-protocol.md`](bus-protocol.md), including 0xFFFF for "on" and zero after reset | R1 |
| Bus-loss timeout | All valves close after 60 s without a valid request to this node | The controller polls every 5 s, so 60 s is twelve missed polls |
| Run-time limit | A valve closes after 120 min open | Home Assistant's longest setting is 90 min; this is the backstop when Home Assistant fails and the controller keeps polling |
| One valve per node | Opening one output closes the node's other outputs and sets their setpoints to 0 | Transformer and cable carry one valve |
| Diagnostics | New registers from 5 upward: monitor state per output, firmware version, address | Registers 0 to 4 keep their meaning |
| Answer delay | The node answers after 3.5 characters of silence, as Modbus prescribes | The old node answered after 1.5 |

The one-valve rule across nodes stays the controller's job. A node cannot see the others.

## Outline and connectors

The enclosure is designed in its own step and decides the final outline. This is the board's
input to it.

```
        x →   0                                        75 mm
     y        ┌───────────────────────────────────────────┐
     ↓   0    │ ○   address    UPDI    moisture         ○ │
              │     switch             sensor             │
           ┌──┤                                           ├──┐
   bus IN  │  │  protection   LOGIC SIDE                  │V1│
   RJ45    │  │  12 V, RS485  microcontroller, regulator  ├──┤
           ├──┤                                           │V2│  valve plugs,
   bus OUT │  │            ═════ isolation gap ═════      ├──┤  two poles each:
   RJ45    │  │                                           │V3│  output and common
           └──┤  24 VAC       24 VAC SIDE                 ├──┤
              │  TVS, fuse    triacs, optocouplers        │V4│
        52    │ ○                                       ○ ├──┘
              └───────────────────────────────────────────┘
```

| Item | Proposal |
|---|---|
| Board | About 75 × 52 mm, two layers, 1.6 mm, parts on top |
| Mounting | Four holes for M3, 4 mm from the edges in the corners |
| Bus | Two RJ45 jacks, 8 poles, unshielded, right angle, side by side on the left edge |
| Valve plugs | Four 2-pole pluggable screw terminals, 5.08 mm pitch, right-angle headers on the right edge, two populated |
| Moisture sensor | 3-pole pluggable terminal, 3.81 mm pitch, on the top edge: 5 V, ground, signal |
| Height | About 14 mm above the board at the jacks, 3 mm below for the through-hole pins |
| Enclosure | Cable entries on two opposite walls: two bus cables on one, valve wires and sensor on the other |

### Bus: RJ45

The bus cable is crimped with RJ45 plugs in the standard T568B order. With the colours of
[`bus-protocol.md`](bus-protocol.md) that gives:

| Pin | Wire | Function |
|---|---|---|
| 1 | orange/white | 24 VAC |
| 2 | orange | 24 VAC |
| 3 | green/white | +12 V |
| 4 | blue | spare |
| 5 | blue/white | spare |
| 6 | green | 12 V − |
| 7 | brown/white | RS485 B |
| 8 | brown | RS485 A |

Jack: Amphenol RJHSE-5080, rated 1.5 A and 125 V AC per contact, tested with 1000 V AC between
contacts, 20 mΩ contact resistance, −55 to 85 °C, 750 mating cycles (Amphenol RJHSE series
datasheet, p. 1). The largest current is 0.37 A on the 24 VAC pair.

Why RJ45 and not the screw terminals of the baseline:

- One plug replaces eight screws, and a cable tester checks each cable segment after crimping.
- A node can be taken out and bridged with a coupler. With screw plugs an unplugged node
  interrupted the bus for the nodes behind it.
- The contacts of an RJ45 plug cut into the conductor. That is the termination this cable is made
  for. Aluminium under a screw yields over time and the screw loosens.
- Two wires under one screw were never needed, because the bus still passes through the board
  from jack to jack.

What it costs:

- In the jack, the 24 VAC contacts sit next to the +12 V contact at 1 mm pitch, where the screw
  terminals had the spare pair in between. The jack is tested with 1000 V AC between contacts, and
  inside the cable the pairs are no further apart. A flashover there ends on the 12 V supply,
  where the TVS D1 clamps it, and not on the 5 V logic. The 3 mm rule still holds between the
  24 VAC section and the logic.
- The plugs must be the type for solid conductors, and crimping needs the tool.
- Two functions that the screw plug offered by rewiring move onto the board as solder jumpers,
  open by default: swapping A and B, and connecting the spare pair in parallel to the 24 VAC pair.

Why both jacks on one edge. The eight pass-through connections are then a few millimetres long.
A surge that travels along the cable passes the node at its edge, and the TVS diodes sit right
there. The 24 VAC pair leaves the pass-through along one long edge to the triacs; the logic takes
the other long edge.

### Cable entries

A seal needs a round jacket, and two things here are not round: the crimped plug is larger than
the cable, and each valve has two single wires.

The owner prints the seals. Each entry is an opening in the enclosure wall with a conical seat, a
split insert of TPU that is laid around the cable, and a nut of PETG that presses the insert into
the cone.

- Bus cable: the opening is large enough for the RJ45 plug. The insert has one hole for the cable
  jacket and one slit. The cable stays crimped when the node or the enclosure is taken out.
- Valve wires: one insert with two holes, one per wire, each with a slit.
- Moisture sensor cable: as the bus cable, smaller.

A slit seals less well than a closed ring. Whether it holds is decided by the water bath test of
the enclosure step, on a printed sample with the real cable and real valve wires. The fallback
needs no other enclosure: an insert without a slit, pushed onto the cable before the plug is
crimped.

Needed for the enclosure step: the outer diameter of the bus cable and of a valve wire, and the
plug's cross-section, measured with a caliper.

The valve plugs are through-hole parts, as are the jacks. Whether JLCPCB solders them or the owner
does is decided with the bill of materials; both work.

## Layout rules

The autorouter knows nothing about surges or isolation. These rules go into the layout script
before routing.

| Rule | Value |
|---|---|
| Net class "AC": the 24 VAC pair, fused common, valve outputs, gate and snubber nets, monitor LED nets | Track width 0.8 mm, clearance 0.5 mm inside the class |
| Clearance between class "AC" and every other net | 3.0 mm. Exception: at the two jacks and on the pass-through between them the jack's pin spacing sets it |
| Isolation gap | No copper on either layer under the optocouplers between their pin rows, and none in a 3 mm strip along the boundary |
| Ground zone | On the logic half only |
| Net class "bus power": +12 V and ground pass-through | Track width 0.8 mm |
| Protection first | Each TVS sits at the jacks, before any other part on that net, with a short and wide connection to its return (TI SLLSF20B, 11.1, p. 21) |
| Triac cooling | At least 0.5 cm² of copper under each DPAK tab; the 70 K/W figure assumes it |
| Spare pair | Passed through jack to jack; two open solder jumpers can connect it to the 24 VAC pair |
| A and B | Two solder jumpers at the transceiver select which bus wire is A; default brown |

The 3 mm is a design choice, not a figure from a safety standard: both sides are extra-low
voltage. It is the distance that the smallest part across the barrier allows comfortably, and it
is more than the cable offers between its own pairs.

## Part selection

LCSC number, JLCPCB class, stock and unit price at the lowest quantity tier, read on 2026-11-14.
Quantity is per board with two outputs populated.

| Ref | Part | Qty | LCSC | Class | Stock | Price |
|---|---|---|---|---|---|---|
| U1 | ATtiny1616-MNR, VQFN-20 | 1 | C507118 | extended | 10,257 | $1.25 |
| U2 | THVD2410DR, SOIC-8 | 1 | C1849398 | extended | 6,398 | $0.92 |
| U3 | HT7550-1, SOT-89 (Holtek) | 1 | C16106 | extended, preferred | 175,814 | $0.13 |
| Q1, Q2 | T410-600B-TR, DPAK | 2 | C2970064 | extended | 1,320 | $0.71 |
| U4, U5 | EL3053S1(TA)-V, optotriac | 2 | C7183129 | extended | 7,783 | $0.22 |
| U6, U7 | LTV-814S-TA1, AC optocoupler | 2 | C125118 | extended | 31,511 | $0.17 |
| D1 | SMBJ15CA-E3/52 (Vishay) | 1 | C435933 | extended | 21,528 | $0.19 |
| D2 | M7 (MDD) | 1 | C95872 | basic | 6,392,352 | $0.01 |
| D3 | PSM712-LF-T7 (ProTek) | 1 | C32677 | basic | 138,344 | $0.34 |
| D4 | SMBJ48CA (Littelfuse) | 1 | C151264 | extended | 5,591 | $0.15 |
| F1 | mSMD020-60V | 1 | C70108 | extended | 24,006 | $0.05 |
| F2 | mSMD050-60V | 1 | C70113 | extended | 146,918 | $0.09 |
| SW1 | DSHP04TSGET, 4-pole switch, 1.27 mm | 1 | C40736 | extended | 23,786 | $0.54 |
| C | 100 nF 100 V X7R 0805, snubber | 2 | C106243 | extended | 1,620,552 | $0.01 |
| C | 10 µF 50 V X5R 1206, regulator input | 1 | C13585 | basic | 3,594,662 | $0.12 |
| LED | Green 0603, already in `lib/jlcpcb-parts.csv` | 1 | C72043 | extended | not read | |
| J1, J2 | RJ45 jack RJHSE-5080 (Amphenol) | 2 | C599441 | extended | 617 | $0.94 |
| J3, J4 | 2-pole header 5.08 mm, right angle | 2 | C441204 | extended | 45,581 | $0.05 |
| | 2-pole plug 5.08 mm | 2 | C440880 | extended | 43,965 | $0.15 |

Resistors and the remaining capacitors are JLCPCB basic parts in 0603 and 0805; their numbers are
fixed with the bill of materials. The UPDI header, the termination resistor and the bias
resistors are footprints.

Parts for one board come to about $9. Most parts are "extended", for which JLCPCB charges a
set-up fee per part type and order; the exact amount is part of the cost estimate before the
order.

Not verified from a datasheet, because the file could not be read: the address switch (24 V,
25 mA and −40 to 85 °C are from the JLCPCB listing) and the valve terminal blocks (300 V and 15 A
from the listing). Neither carries a rating that a design decision depends on; their dimensions
are checked against the footprint at the schematic stage. The 10 µF capacitor is X5R, rated to
85 °C, which matches R11.

Second choices, if stock runs out: the Molex 95501-2881 (C293728, 4,886 in stock) for the jack,
once its datasheet is read. Z0107MN (C71218, 1 A, SOT-223) is not a replacement for the
triac, because it lacks the margin for a shorted valve wire; the T405-600B-TR (C283473, same
datasheet, 139 in stock) is. EL3052S(TA) (C5687675, 20,027 in stock) replaces the optotriac with
a 150 Ω LED resistor, because it needs 10 mA.

## Deviations from the baseline

| Baseline | This specification | Reason |
|---|---|---|
| ATtiny1614 | ATtiny1616 in VQFN-20 | 16 pins needed, 11 available; better stock and price |
| SM712 | PSM712 | Same part, JLCPCB basic |
| Triac outputs, drive not stated | Triacs fired through optotriacs, 24 VAC isolated from logic | Ground shift, surge path, fault containment |
| Valve current sensing, optional | Voltage monitor across each triac, populated | No voltage drop; finds a broken wire before opening |
| Termination via solder jumper | Kept, but open on every node; bias footprints added | Budget; idle level with the existing controller module |
| Bus passed through | Kept, including the spare pair | A later branch can use the spare pair at any box |
| Pluggable screw terminals | RJ45 jacks for the bus; screw plugs only for the valves | One plug, testable, bridged by a coupler, right termination for the cable |
| Optional moisture input | Dropped after sign-off | The sensor on the installed system never worked properly (owner, 2026-11-14) |

Everything else follows the baseline: RS485 transceiver with TVS, 12 V input with reverse
polarity protection, resettable fuse and TVS, 5 V regulator, two of four outputs populated, DIP
switch address, two layers, status LED.

## Answers to the existing system

Weaknesses and open points from [`existing-system.md`](existing-system.md) and
[`bus-protocol.md`](bus-protocol.md), in their order there.

| Point | Answer |
|---|---|
| Bus down, receive LED lit permanently | The new node cannot hold the bus: hardware driver enable with pull-down, watchdog locked on, thermal shutdown. A fault is located by pulling OUT plugs box by box. All old nodes come out before the first new one goes in. |
| The bus does not tolerate another node or a terminator | Each new node loads the bus with 1/8 unit load and no terminator. Its driver drives both levels, so its answers do not depend on bias resistors. |
| No close on bus loss | 60 s timeout in the node; a reset closes the valves. |
| Both outputs can be on at once | The node closes its other outputs when one opens. |
| No feedback | Output monitor per valve, reported in new registers. |
| Software serial on an RC oscillator | Hardware USART; oscillator within ±2 % and corrected per chip. |
| One firmware build per node | Address switch. |
| Relay coil current over the cable | No relay. One open valve costs 16 mA. Far node at 10.8 V in today's configuration where the old design reached about 6 V. |
| 8 VA transformer | The node takes nothing from 24 VAC except the valve's own current and about 0.04 VA per connected valve for monitor and snubber. Sizing the replacement is part of the controller specification. This page hands over one requirement: limit the short-circuit current, see [Faults on the 24 VAC side](#faults-on-the-24-vac-side). |
| Transformer open-circuit voltage unknown | The node tolerates up to 33.9 V RMS. A measurement above 33 V changes one TVS. |
| Cable is copper-clad aluminium, 26 Ω loop estimated | The 12 V budget holds with the estimate. For the valves the node adds about 1 V of drop that a relay did not have; tested first on the first board. If the far valve does not pull in, the spare pair can double the 24 VAC pair through two solder jumpers on each node. That gives up the branch reserve, so it is the owner's call at that point. |
| Aluminium strands break and corrode | RJ45 plugs for solid wire cut into the conductor and need no re-tightening; the cable entry is the strain relief; sealed enclosure. |
| Fixed 120 Ω on every RS485 module (hypothesis) | It no longer matters once the old nodes are out: the one remaining module at the controller may carry its 120 Ω. The two-minute measurement is still worth doing because it explains the old fault. |
| Solenoid tolerance, switch-on duration and pull-in voltage unknown | The triac has a margin of ten on current. The pull-in voltage stays the open risk named above and is measured on the first board. |
| One-valve rule not enforced | In the node for its own outputs; across nodes in the controller. |
| Maximum run time only in Home Assistant | 120 min limit in the node. |
| RS485 polarity | Two solder jumpers swap A and B. |
| Termination and bias on the existing bus | Idle voltage measured at commissioning; bias footprints on every node. |
| Controller response timeout, retries, request spacing | The node answers within 4 ms after a request ends, faster than any ESPHome default. Recording the ESPHome version stays open for the controller. |
| Registers of the generation-1 nodes | Not needed. The controller uses registers 0 and 2 only, and the new node implements the generation-2 map. |
| The value 0xFFFF for "on" | Any non-zero value opens the valve and reads back as written. |

## Open points

| Point | Needed for | Who, when |
|---|---|---|
| Does the farthest valve pull in through a triac? | Confirms the output design | First board, before the rest is installed |
| Does a valve close with 2 mA of off-state current? | Monitor and snubber values | First board |
| Idle voltage between A and B with the existing controller module | Whether bias resistors are populated | Owner, multimeter, at commissioning |
| Open-circuit voltage of the transformer | TVS on the 24 VAC pair | Owner, multimeter, any time |
| Inside dimensions of the valve boxes | Size limit of the enclosure | Owner, before the enclosure is designed |
| Diameters of bus cable and valve wire, cross-section of the RJ45 plug | Split inserts | Owner, caliper, before the enclosure is designed |
| Do the split inserts stay tight? | Cable entries | Water bath test in the enclosure step |
| Conformal coating | Moisture margin | Owner's decision before bring-up |
| JLCPCB class and stock of every part | Order | Before the order, on jlcpcb.com |

## Sources

| Document | Used for |
|---|---|
| Microchip, *ATtiny1614/1616/1617 Complete Datasheet*, DS40002204A, 2020 | Pin functions (p. 18), watchdog (p. 170), RS-485 mode (p. 327), absolute maximum ratings (p. 505), supply current (p. 508), brown-out levels (p. 510), oscillator (p. 511), pin drive (p. 513) |
| Texas Instruments, *THVD2410, THVD2450*, SLLSF20B, revised October 2021 | Features (p. 1), pins (p. 3), absolute maximum and ESD ratings (p. 4), electrical characteristics (p. 6), layout guidelines (p. 21) |
| STMicroelectronics, *T4 series, 4 A triacs*, DocID7699 Rev 9, November 2016 | Tables 3 to 6 (p. 2 and 3) |
| Everlight, *6 pin DIP random-phase triac driver photocoupler EL301X, EL302X, EL305X*, DPC-0000059 Rev. 12, 2018 | Absolute maximum ratings (p. 2), electro-optical characteristics (p. 3 and 4) |
| Lite-On, *LTV-8x4 series*, BNS-OD-FC001/A4, Revision J | Features (p. 2), ratings and characteristics (p. 9 and 10) |
| Holtek, *HT75xx-1, 100 mA low power LDO*, Rev. 2.80, 2024-04-10 | Absolute maximum ratings and thermal data (p. 4), HT7550-1 table (p. 8) |
| ProTek Devices, *PSM712*, 05094.R8, 10/12 | Electrical characteristics (p. 2) |
| Vishay, *SMBJ5.0A thru SMBJ188CA*, document 88392, 2019-01-24 | Electrical characteristics (p. 2) |
| Littelfuse, *SMBJ series*, revised 2025-07-04 | Electrical characteristics table (p. 2) |
| Techfuse, *mSMD series* and *mSMD010-60V specification sheet* QR0429 | Performance table, hold current versus temperature |
| MDD, *M1 thru M7*, Rev. 2025A5 | Ratings (p. 1) |
| Amphenol, *Modular Jack, RJHSE Series* | Electrical and mechanical performance (p. 1) |
| JLCPCB parts search, 2026-11-14 | Stock, class, price; ratings of switch and terminal blocks |
