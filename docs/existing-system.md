# Existing system

The installation the new boards replace, as far as it constrains their design. Wiring, registers
and timing of the bus are in [`bus-protocol.md`](bus-protocol.md) and are not repeated here.

Sources, read on 2026-11-14: the owner's build notes of 2025-07-01, the ESPHome configuration of
the controller, the generation-2 node firmware, the Home Assistant automations and scripts (read
through the Home Assistant API, nothing changed), the Hunter documents cited below, and the
owner's statements and product listings for transformer, cable and RS485 module (2026-11-14). None
of the hardware was opened or measured for this document.

## Overview

```
shed (dry)                               buried CAT-6, daisy chain, < 100 m
┌──────────────────────────────┐         ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
│ 24 VAC transformer ──────────┼─ 24 VAC ┤ node 1 ├───┤ node 2 ├───┤ node 3 ├───┤ node 4 │
│ USB supply ─ step-up 12 V ───┼─ 12 VDC ┤ 1 valve│   │ 2 valves   │ 1 valve│   │ 2 valves
│ D1 Mini (ESPHome) ─ RS485 ───┼─ RS485  └────────┘   └────────┘   └────────┘   └────────┘
└──────────────────────────────┘
        │ Wi-Fi
   Home Assistant
```

The drawing shows the bus addresses, not the order of the boxes along the cable.

## Controller

- Wemos D1 Mini (ESP8266) running ESPHome with the `modbus_controller` component; UART on pins D1
  (TX) and D2 (RX).
- TTL-to-RS485 adapter module with automatic direction switching, the same type as in every node
  (see [RS485 adapter module](#rs485-adapter-module)).
- USB power supply for the D1 Mini, and from the same supply a step-up converter set to 12 V that
  feeds the nodes over the cable.
- 24 VAC transformer for the valves, connected straight to the 24 VAC pair (see
  [Transformer](#transformer)).
- Entities offered to Home Assistant: six valve switches named "Garten Relais 1", "2.1", "2.2",
  "3", "4.1" and "4.2" (node and valve number), one "Controller *n* offline" sensor per node, and a
  restart switch. The new controller has to offer the same switch names so that the Home Assistant
  side keeps working.
- The ESPHome configuration contains no interlock, no maximum run time and no schedule. It also
  enables ESPHome's built-in web page, from which every valve can be switched without Home
  Assistant.

## Nodes

Four nodes, six valves. Each node sits in a valve box in the ground together with its valves.

| | Generation 1 | Generation 2 |
|---|---|---|
| In use | three nodes | one node |
| Build | modules hand-soldered on perfboard | custom board, corrected by hand after assembly |
| Microcontroller | Digispark ATtiny85 board, on-board regulator fed from 12 V | bare ATtiny85, 8 MHz internal oscillator |
| RS485 | adapter module, same type in every node | the same adapter module |
| Valve outputs | 1 or 2 relay modules | 2 relay outputs on PB0 and PB1 |
| Serial | software serial | software serial, RX on PB4, TX on PB3 |
| Extras | soil moisture sensor | none in the firmware |
| Programming | USB bootloader (micronucleus) | ISP, PlatformIO |
| Firmware source | not available | available, 83 lines |
| Address | compiled in | compiled in (`#define deviceID`) |

The generation-2 board is deliberately not used as a reference for the new design (owner's
decision, 2026-11-14): it was a first attempt and its schematic would only anchor the new one.
What carries over from the existing nodes is the behaviour on the bus, not the circuit.

What the generation-2 firmware does, in full: it configures the Modbus library, then in an endless
loop processes one pending request and sets each relay pin from its setpoint register. There is no
watchdog, no timeout, no stored state and no fault handling.

### Known weaknesses

Found by reading the firmware and the notes, and reported by the owner.

- **The bus does not tolerate another node or a terminator.** The owner's attempt to convert a
  further node made communication with all nodes collapse, and so did adding a termination
  resistor. A likely cause is described under [RS485 adapter module](#rs485-adapter-module). The
  new node has to be designed for this bus as it is, because old and new nodes share it during the
  swap.

- **No close on bus loss.** A node holds an open valve for as long as it has power.
- **Both outputs can be on at once.** Nothing in the node limits it to one valve.
- **No feedback.** The state registers repeat the setpoint; a broken solenoid wire or a blown
  transformer fuse is invisible.
- **Software serial on an RC oscillator.** Bit timing depends on the internal oscillator, which
  drifts with temperature and supply voltage. The error counter in register 4 would show the
  effect; nobody reads it.
- **One firmware build per node.** The address is a compile-time constant.
- **Relay coil current comes over the cable.** The owner's test with 100 m of cable showed that a
  5 V supply sags too far for the relay to pull in, which is why the bus carries 12 V. By the
  owner's calculation, six nodes and one energised relay at the far end of 100 m pull the 12 V down
  to about 6 V. That calculation is the second reason for the one-valve rule, next to the
  transformer.

## Transformer

Evolution BT8-8, a DIN-rail bell transformer: 220 V 50 Hz primary, secondary taps 8 V, 12 V and
24 V, rated power **8 VA**. Source: the product listing and the print on the housing; no datasheet
was found.

- 8 VA at 24 V is 0.33 A. One PGV-101 holds at 5.0 VA and pulls 8.9 VA at switch-on (see
  [Valves](#valves)): one valve fits the rating while holding and exceeds it briefly at switch-on,
  two valves holding (10 VA) exceed it permanently. This is where the one-valve rule comes from.
- Open-circuit voltage, regulation and the kind of overload protection are not known.
- The baseline for the new controller, to feed valves, bus supply and controller from this one
  transformer, does not fit: a holding valve leaves 3 VA for everything else. The controller
  specification has to size a new transformer.

## Cable

Mr. Tronic outdoor Cat 6 installation cable, double jacket, cross separator, **AWG 24, conductors
of copper-clad aluminium (CCA)**. Source: product listing; no datasheet with a resistance figure.

The conductor material matters more than the category. Estimate from the cross-section of AWG 24
(0.205 mm²) and the resistivities of copper and aluminium, to be replaced by a measurement:

| | Copper AWG 24 | CCA AWG 24 (estimate) |
|---|---|---|
| Resistance per conductor | 0.084 Ω/m | about 0.13 Ω/m |
| Loop resistance at 100 m (out and back) | 17 Ω | about 26 Ω |
| Drop at 0.21 A (one valve holding) | 3.5 V | about 5.5 V |
| Drop at 0.37 A (one valve at switch-on) | 6.2 V | about 9.6 V |

- These figures are for a valve at the far end of 100 m; the installed cable is shorter. Even so,
  a far valve sees clearly less than 24 V at switch-on, before the sag of an 8 VA transformer is
  counted. That the valves pull in reliably today is an observation, not a margin.
- The 12 V supply runs over a pair of the same kind; the estimate matches the owner's calculation
  of a drop to about 6 V at 100 m.
- CCA strands break more easily than copper when nicked or bent repeatedly and corrode at the
  contact when moisture reaches it. Terminals and strain relief in the valve box have to allow for
  that.
- The spare blue pair could halve the resistance of one supply if it is not needed for a branch.

## RS485 adapter module

Every node and the controller use the same TTL-to-RS485 module with automatic direction switching
(board marking HW-0519, sold under several brand names). Read from a product photo, not from a
schematic:

- Bus side: terminals A+, B− and ground, two resettable fuses and three protection diodes.
- A resistor marked `121` (120 Ω) sits directly at the bus terminals.
- An 8-pin transceiver and a 14-pin logic chip that derives the driver enable from the transmit
  data.

**Hypothesis: every module carries a fixed 120 Ω termination.** With five modules on the bus that
is 24 Ω between the bus wires where a correctly terminated bus has 60 Ω. Modules of this kind
drive the bus actively only for one logic level and leave the other to their bias resistors,
which a load this heavy pulls close to zero. That would explain both observations: a sixth module
or an extra terminator lowers the resistance further and the idle level disappears.

Test, two minutes: measure the resistance between A and B on a loose spare module (expected about
120 Ω), and between the brown wires of the powered-down bus (expected about 24 Ω). If the
hypothesis holds, removing the resistor from the modules that are not at the ends of the cable
repairs the existing bus, and the new node must be built without a fixed terminator.

## Valves

Hunter PGV-101 with 1" male thread and a 24 VAC solenoid, one per zone, six in total.

| | 50 Hz | 60 Hz |
|---|---|---|
| Inrush current | 370 mA | 350 mA |
| Holding current | 210 mA | 190 mA |

Source: Hunter Industries, product sheet *1" PGV* (generated 2023-06-27), page 1, "Solenoid
Specifications". The same four figures appear in the Hunter brochure *PGV Valves*, INT-361-EM H
02/17, page 2, "Operating Specifications".

- The installation runs on 50 Hz mains, so the 50 Hz column applies: at 24 V that is 8.9 VA
  inrush and 5.0 VA holding per valve.
- Earlier planning used 0.4 A and 0.23 A from memory. The datasheet values are about 8 % lower;
  the earlier figures were on the safe side.
- Neither document states a tolerance, the duration of the inrush, a minimum pull-in voltage or
  the coil's inductance and resistance. Sizing of the output switch and its protection needs
  margin on these figures or a measurement on a real valve.
- Other ratings on the same page: recommended pressure 20 to 150 PSI, temperature rating 150 °F.

## One-valve rule in Home Assistant

The rule: never more than one valve open, because of the transformer and the 12 V drop. Question:
do the Home Assistant automations keep to it?

**Result: the automated sequence does, but nothing enforces the rule.** Two valves can be opened
at the same time by hand, and Home Assistant does not notice or prevent it.

What exists (all 160 automations and scripts were searched for the six switches):

| Item | What it does | With regard to the rule |
|---|---|---|
| Script "water everything" | Opens the six valves one after the other: on, wait the configured duration, off, wait 5 s, next. Order 1, 2.1, 2.2, 3, 4.2, 4.1. Started by hand; no automation or schedule starts it. | Keeps to the rule in normal operation. |
| Automation "timer start" | Whenever any of the six switches goes from off to on, restarts a run timer with the configured duration. | Does not look at the other switches. |
| Automation "timer stop" | When the run timer finishes, switches all six valves off. | A maximum run time, not an interlock. |
| Duration setting | 10 to 90 minutes in steps of 10, shared by script and timer. | |
| Automation "controller offline" | Sends a notification when a node goes offline. | |

Where the rule can be broken:

1. **Manual switching.** Each valve is an ordinary switch in Home Assistant and on the
   controller's own web page. Opening a second one works; it only restarts the run timer, so both
   stay open for the full duration.
2. **Manual switching while the script runs.** Same effect; the script does not check the other
   valves before it opens the next one.
3. **A lost "off".** The script waits 5 s after switching a valve off and then opens the next one
   without checking that the first one closed. If the off command does not reach the node (node
   offline, bus fault), two valves are open until the run timer of the second one ends.

Related findings:

- The script cannot run twice in parallel (mode "single"), so starting it again while it runs
  does nothing.
- Script delay and run timer use the same duration. At the end of each zone the script's "off"
  and the timer's "all off" arrive within moments of each other; both only close valves, so the
  race is harmless.
- The run timer survives a Home Assistant restart; the script does not. After a restart in the
  middle of a run the open valve is closed by the timer and the remaining zones are skipped.
- The maximum run time lives in Home Assistant alone. If Home Assistant, the Wi-Fi link or the
  controller fails while a valve is open, nothing closes it (see "No close on bus loss" above).

Consequence for the new design: the interlock belongs in the controller, and the bus-loss timeout
in the node, so that the rule and the run-time limit hold without Home Assistant.

## Open points

| Point | Needed for | Who |
|---|---|---|
| Termination on the RS485 modules (test above) | Whether new nodes can join the existing bus at all | Owner, multimeter |
| Loop resistance of the cable | Voltage at the far valve and on the 12 V supply | Short the spare blue pair at the last box and measure at the controller |
| Open-circuit voltage of the transformer, and its voltage with one valve open | Sizing of the replacement | Measurement |
| Current drawn by a node, idle and with a relay energised | 12 V budget during the mixed operation of old and new nodes | Measurement |
| Solenoid inrush duration and pull-in voltage | Output switch sizing | Measurement on a spare valve |
| Bus points listed in [`bus-protocol.md`](bus-protocol.md#open-points) | | |
