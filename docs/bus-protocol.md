# Bus and protocol

What runs on the buried cable today: wiring, serial settings, addresses, registers and timing. The
new valve nodes keep cable, addresses and registers, so the existing controller and its Home
Assistant entities work with them unchanged until the controller is replaced as well. Old and new
nodes never share the bus: all old nodes are removed before the first new one is connected. The
hardware around the bus is described in
[`existing-system.md`](existing-system.md).

Sources, read on 2026-11-14:

- **Node firmware** (generation 2, ATtiny85): `src/main.cpp`, 83 lines, in the owner's firmware
  repository (not part of this repository).
- **Modbus library** used by that firmware: `SimpleModbusSlaveSoftwareSerial.cpp` from
  [angeloc/simplemodbusng](https://github.com/angeloc/simplemodbusng), `master` branch.
- **Controller configuration**: the ESPHome YAML of the controller (not part of this repository).
- **Owner's build notes** of 2025-07-01 for the cable.

Nothing here was measured on the bus. Statements that follow from reading code are marked by their
source; what still needs a measurement is listed under [Open points](#open-points).

## Cable

One buried CAT-6 cable runs from the controller through every valve box as a daisy chain: the
cable enters a box and leaves it again, there are no stubs. Total length is below 100 m, with at
most 6 boxes.

| Wire | Function |
|---|---|
| brown | RS485 A |
| brown/white | RS485 B |
| green | 12 VDC − |
| green/white | 12 VDC + |
| orange | 24 VAC |
| orange/white | 24 VAC |
| blue | spare |
| blue/white | spare |

- Each function uses one twisted pair. Each supply therefore has a single conductor per direction.
- The spare pair is reserved for a branch: RS485 goes out to the branch on one pair and returns on
  the other, so the bus stays a line electrically. The supplies may branch as a star.
- "A" and "B" are the labels printed on the RS485 adapter modules in use. The letters are not used
  the same way by every transceiver vendor; see [Open points](#open-points).
- The cable has AWG 24 conductors of copper-clad aluminium; resistance and voltage drop are in
  [`existing-system.md`](existing-system.md#cable).
- Termination and bias: the adapter modules carry 4.7 kΩ bias resistors and a 120 Ω terminator
  that is across the bus only if a pad on the module is bridged; see
  [`existing-system.md`](existing-system.md#rs485-adapter-module). The new valve nodes carry
  neither; termination and bias sit at the controller only
  ([`existing-system.md`](existing-system.md#bias-at-the-controller)).

## Serial settings

| Setting | Value | Source |
|---|---|---|
| Protocol | Modbus RTU, controller is the only client | ESPHome `modbus_controller` |
| Baud rate | 9600 | firmware `BAUD_RATE`, ESPHome `baud_rate` |
| Frame | 8 data bits, no parity, 1 stop bit | ESPHome `stop_bits: 1` and UART defaults; `SoftwareSerial` on the node supports nothing else |
| Direction control | none in software on either side; the adapter modules switch direction on their own | firmware `RS485_EN 0`, no `flow_control_pin` in ESPHome |

One character is 10 bits, 1.04 ms.

## Addresses

| Address | Valves | Registers in use by the controller |
|---|---|---|
| 1 | 1 | 0 |
| 2 | 2 | 0, 2 |
| 3 | 1 | 0 |
| 4 | 2 | 0, 2 |

Addresses 5 and 6 are free for the two further boxes the cable allows. In the generation-2
firmware the address is a compile-time constant (`#define deviceID`), so each node has its own
firmware build.

Address 0 (broadcast) must not be used. The library accepts broadcast writes, but answers a
broadcast "write single register" as if it were addressed, so every node would reply at once.

## Registers

All registers are 16-bit holding registers, addressed from 0. A generation-2 node has exactly five.

| Register | Name in firmware | Access | Meaning |
|---|---|---|---|
| 0 | `RELAIS` | read/write | Valve 1 setpoint: 0 = closed, any other value = open |
| 1 | `RELAIS_ZUSTAND` | read | Valve 1 state: 1 while the output is driven, else 0 |
| 2 | `RELAIS2` | read/write | Valve 2 setpoint, as register 0 |
| 3 | `RELAIS2_ZUSTAND` | read | Valve 2 state, as register 1 |
| 4 | `TOTAL_ERRORS` | read | Communication error counter since power-up, wraps at 65535 |

Behaviour that a compatible node has to reproduce:

- **Any non-zero setpoint opens the valve.** ESPHome writes 0xFFFF for "on", not 1 (its switch
  writes `0xFFFF & bitmask`, and the configuration sets no bitmask). The command-line scripts in
  the firmware repository write 1. Both must work.
- **A setpoint reads back as written.** After ESPHome switched a valve on, register 0 reads
  0xFFFF. ESPHome treats any non-zero value as "on".
- **Setpoints are zero after reset.** The register array is zero-initialised and not stored, so a
  node that restarts closes its valves and stays closed until the next write.
- **The state registers mirror the setpoint.** They are derived from the setpoint in the same loop
  pass that drives the output pin; they do not measure anything. The controller does not read them.
- **Registers 1, 3 and 4 accept writes without an error** and are overwritten within one loop pass.
- A single-valve node still has all five registers; registers 2 and 3 exist and drive an unused pin.

The error counter increases by one for each: frame with a wrong checksum addressed to the node,
frame shorter than 7 bytes seen on the bus, whoever it was addressed to, exception response sent, write-multiple request with
an inconsistent byte count, receive buffer overflow. A 5-byte exception response from one node
therefore also counts as an error on every other node.

Extensions (valve current, soil moisture, firmware version) go into new registers from 5 upward;
registers 0 to 4 keep their meaning.

## Function codes

| Code | Function | Supported by the node | Used by |
|---|---|---|---|
| 3 | Read holding registers | yes | ESPHome polling, `mbpoll` |
| 6 | Write single register | yes | ESPHome switches, `mbpoll` |
| 16 | Write multiple registers | yes | nobody today |
| any other | | exception 1 (illegal function) | |

Exceptions: a start address above 4 returns exception 2 (illegal data address). A range that
starts inside and ends beyond register 4 returns exception 3 where the Modbus specification
prescribes 2.

Example frames (hex, checksum included):

| Purpose | Request | Response |
|---|---|---|
| Read all registers of node 1 | `01 03 00 00 00 05 85 C9` | `01 03 0A 00 01 00 01 00 00 00 00 00 07 78 24` (valve 1 open, 7 errors) |
| Open valve 2 of node 2, as ESPHome does | `02 06 00 02 FF FF 29 89` | echo of the request |
| Close valve 2 of node 2 | `02 06 00 02 00 00 28 39` | echo of the request |
| Read register 5, which does not exist | `01 03 00 05 00 01 94 0B` | `01 83 02 C0 F1` (exception 2) |

## Timing

### Controller

| What | Value | Source |
|---|---|---|
| Poll interval per node | 5.0 s, 5.2 s, 5.4 s, 5.6 s for addresses 1 to 4 | ESPHome `update_interval` |
| Poll content | function 3 on the switch registers | ESPHome `modbus_controller` switches |
| Valve command | function 6, sent when the switch changes, not on the next poll | ESPHome `modbus_controller` switch |
| Offline detection | per node, exposed to Home Assistant as "Controller *n* offline" | ESPHome `get_module_offline()` |

The staggered intervals keep the four polls from always falling on the same instant. Response
timeout, retries and the pause between two requests are ESPHome defaults; they depend on the
installed ESPHome version, which is not recorded. See [Open points](#open-points).

### Node (generation 2)

| What | Value | Source |
|---|---|---|
| End of frame | 1.56 ms without a new byte (1.5 characters) | library: `T1_5 = 15000000 / baud` µs |
| Hold time after the response | 3.65 ms (3.5 characters) | library: `T3_5 = 35000000 / baud` µs |
| Response start | right after the end of frame is detected; no deliberate delay | library `modbus_update()` |
| Response duration | 8.3 ms for the 8-byte write echo, 15.6 ms for reading all five registers | 10 bits per byte at 9600 baud |
| Setpoint to output pin | in the main-loop pass that follows the response, about 14 ms after the request ended | firmware `loop()` |
| Bus-loss timeout | **none** | firmware `loop()` |

The node is deaf while it transmits: `SoftwareSerial` disables interrupts for each byte it sends.
The controller must therefore not send while a response is on the wire, which a single client that
waits for each response never does.

## What neither side enforces

- **One valve at a time.** The transformer and the 12 V drop on the cable are sized for one open
  valve. The node opens whatever it is told to, on both outputs at once if asked, and the
  controller forwards every switch command. The rule exists only in how Home Assistant is used; see
  [`existing-system.md`](existing-system.md#one-valve-rule-in-home-assistant).
- **Closing on bus loss.** A node keeps its last setpoint for as long as it has power. If the
  controller, its Wi-Fi link or Home Assistant fails while a valve is open, the valve stays open.
- **Confirmation.** The state registers repeat the setpoint. There is no feedback that current
  flows through the solenoid.

## Open points

| Point | How to close it |
|---|---|
| Polarity of the RS485 pair | Measure the idle bus and note which wire is positive against the other, then match that to the pin names in the new transceiver's datasheet. The letters alone do not settle it. The valve node has brown on pin A and no way to swap on the board; a reversed pair is swapped at the controller's terminals or in the plug. |
| Termination and bias on the existing bus | A spare module was measured on 2026-11-15. Left open: whether the terminator is bridged on the controller's module; see [`existing-system.md`](existing-system.md#rs485-adapter-module). |
| Controller response timeout, retries, request spacing | Record the ESPHome version when the controller is next built, or capture the bus with a USB RS485 adapter. |
| Registers of the three generation-1 nodes | Their source is not available. Read registers 0 to 9 of each generation-1 node with `mbpoll`; an exception 2 marks the end of the map. |
| The value 0xFFFF for "on" | Follows from the ESPHome source (`dev` branch, 2026-11-14), not from a capture. Confirm by reading register 0 while a valve is open. |
