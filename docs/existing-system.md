# Existing system

The installation the new boards replace, as far as it constrains their design. Wiring, registers
and timing of the bus are in [`bus-protocol.md`](bus-protocol.md) and are not repeated here.

Sources, read on 2026-11-14: the owner's build notes of 2025-07-01, the ESPHome configuration of
the controller, the generation-2 node firmware, the Home Assistant automations and scripts (read
through the Home Assistant API, nothing changed), and the Hunter documents cited below. None of
the hardware was opened or measured for this document.

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
- TTL-to-RS485 adapter module with automatic direction switching.
- USB power supply for the D1 Mini, and from the same supply a step-up converter set to 12 V that
  feeds the nodes over the cable.
- 24 VAC transformer for the valves, connected straight to the 24 VAC pair. Its rating is not
  documented.
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
| Build | hand-wired modules | custom board drawn in EasyEDA |
| Microcontroller | Digispark ATtiny85 board, on-board regulator fed from 12 V | bare ATtiny85, 8 MHz internal oscillator |
| RS485 | TTL-to-RS485 adapter module, automatic direction switching | automatic direction switching (firmware drives no enable pin) |
| Valve outputs | 1 or 2 relay modules | 2 relay outputs on PB0 and PB1 |
| Serial | software serial | software serial, RX on PB4, TX on PB3 |
| Extras | soil moisture sensor | none in the firmware |
| Programming | USB bootloader (micronucleus) | ISP, PlatformIO |
| Firmware source | not available | available, 83 lines |
| Address | compiled in | compiled in (`#define deviceID`) |

Which of the four nodes belongs to which generation is not documented.

What the generation-2 firmware does, in full: it configures the Modbus library, then in an endless
loop processes one pending request and sets each relay pin from its setpoint register. There is no
watchdog, no timeout, no stored state and no fault handling.

### Known weaknesses

Found by reading the firmware and the notes; the owner's defect list for the generation-2 board is
still missing (see [Open points](#open-points)).

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
| Schematic of the generation-2 board (EasyEDA) | Valve node specification: which parts and protection exist today | Owner provides |
| Defect list of the generation-2 board | Valve node specification: every known defect needs an answer | Owner provides |
| Which nodes are generation 1, which generation 2 | Swap order; register map of generation 1 | Owner |
| Rating of the 24 VAC transformer (VA, fuse) | Whether it stays, and the controller's 24 VAC input | Owner reads the type plate |
| Conductor cross-section of the buried cable | Voltage drop on 12 V and 24 VAC over 100 m | Owner reads the cable print, or a resistance measurement |
| Current drawn by a node, idle and with a relay energised | 12 V budget during the mixed operation of old and new nodes | Measurement |
| Solenoid inrush duration and pull-in voltage | Output switch sizing | Measurement on a spare valve |
| Bus points listed in [`bus-protocol.md`](bus-protocol.md#open-points) | | |
