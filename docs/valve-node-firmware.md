# Valve node: firmware

What the valve node's firmware does on the bus, how it is built and tested, and what is still
untested. The circuit it runs on is in [`valve-node-spec.md`](valve-node-spec.md); its
"Behaviour (input for the firmware)" fixed the timeouts and the one-valve rule, and this page is
the firmware specification announced there.

Status: written and tested on the computer against a simulated bus. No board exists yet, so
nothing here has run on an ATtiny1616. [Not tested yet](#not-tested-yet) lists what the first board
has to show.

Sources are in [`firmware/valve-node/`](../firmware/valve-node/):

| File | Content |
|---|---|
| `core/` | The core: Modbus RTU server, register map, valve logic. Plain C++ without hardware access |
| `src/main.cpp` | The ATtiny1616 around the core: clock, pins, serial port, timer, ADC, watchdog |
| `sim/sim.cpp` | Simulator: the same core as one or more nodes on a pseudo-terminal |
| `test/test_node.cpp` | Unit tests of the core with a clock the test controls |
| `bench.py`, `bench.html` | Test bench in the browser on top of the simulator |
| `bustest.py` | Bus test: plays the controller on a serial line, against the simulator or a board |
| `Makefile` | Build rules, compiler flags, fuses |

## Registers

All registers are 16-bit holding registers, addressed from 0. Registers 0 to 4 are the map of the
nodes this one replaces ([`bus-protocol.md`](bus-protocol.md#registers)); the existing controller
uses 0 and 2 only. Everything new is in registers 5 to 13.

| Register | Access | Meaning |
|---|---|---|
| 0 | read/write | Valve 1 setpoint: 0 closes, any other value opens. Reads back as written |
| 1 | read | Valve 1 state: 1 while output 1 is driven, else 0 |
| 2 | read/write | Valve 2 setpoint |
| 3 | read | Valve 2 state |
| 4 | read | Communication errors since reset, wraps at 65535 |
| 5 | read | Output 1 monitor: bit 0 = output driven, bit 1 = fault |
| 6 | read | Output 2 monitor |
| 7 | read | Moisture input, raw ADC value 0 to 1023 against the 5 V supply |
| 8 | read | Firmware version, major in the high byte, minor in the low byte: 0x0100 |
| 9 | read | Address read from the switch at reset |
| 10 | read | Why valve 1 closed last: 0 controller, 1 bus-loss timeout, 2 run-time limit, 3 the other valve was opened |
| 11 | read | Why valve 2 closed last |
| 12 | read | Reset cause, the microcontroller's reset flags: 1 power-on, 2 brown-out, 4 reset pin, 8 watchdog, 16 software, 32 UPDI |
| 13 | read | Minutes since reset, stops at 65535 |

A write to a register marked "read" is accepted and changes nothing, as on the old nodes.

Monitor registers 5 and 6 take four values:

| Value | Meaning |
|---|---|
| 0 | Closed; 24 VAC, wire and solenoid are there |
| 1 | Open; the triac conducts |
| 2 | Closed, fault: no voltage across the triac. 24 VAC missing, fuse F2 tripped, wire or solenoid open, or the triac is shorted |
| 3 | Open, fault: voltage across the triac, so it did not fire |

The monitor reports and does nothing else: a fault closes no valve. For 100 ms after an output
switched, the register reports no fault. An output without a solenoid reads 2; on a one-valve
node that is register 6, always. Register 10 or 11 returns to 0 when its valve is opened again.
Register 7 is meaningless while no sensor is connected: the input floats.

## Behaviour

| Behaviour | Value | Old nodes |
|---|---|---|
| Setpoints after reset | 0, both valves closed | same |
| "On" value | any non-zero value; ESPHome writes 0xFFFF | same |
| Bus loss | 60 s without a valid request to this node close both valves and set their setpoints to 0 | valve stayed open |
| Run-time limit | a valve closes 120 min after it opened; writing its setpoint again while it is open does not extend the time | none |
| One valve per node | opening one valve closes the other and sets its setpoint to 0 | both could be open |
| Address | from the switch, 1 to 15, read once at reset | compiled in |
| Switch at 0 | the node stays off the bus: it answers nothing, accepts no broadcast and opens no valve. The LED blinks fast | |

A valid request is one that is addressed to this node, has a correct checksum and is answered
without an exception. Requests to other nodes, broadcasts and requests that end in an exception
do not count against the bus-loss timeout.

After the node closed a valve by itself, the setpoint register reads 0. The controller's next
poll therefore shows the valve as off in Home Assistant, and register 10 or 11 says why.

If one "write multiple registers" request opens both valves, valve 2 stays open: writes are
applied in register order and the later one wins.

### Status LED

| Pattern | Meaning |
|---|---|
| Fast blinking, 5 Hz | Switch at 0: no valid address |
| Slow blinking, 1 Hz | No valid request for 60 s, or none since reset |
| Dark, a flash for each answered request | Controller present, valves closed |
| On, a short gap for each answered request | A valve is open |

## Protocol

Modbus RTU, 9600 baud, 8N1, as in [`bus-protocol.md`](bus-protocol.md).

| Function | Supported |
|---|---|
| 3, read holding registers | yes |
| 6, write single register | yes |
| 16, write multiple registers | yes |
| any other | exception 1 |

| Case | Answer |
|---|---|
| Register or range outside 0 to 13 | exception 2 |
| Count of 0, count above the Modbus limit, byte count or frame length that does not fit the function | exception 3 |
| Wrong checksum, frame shorter than 4 bytes, frame longer than 64 bytes | none |
| Broadcast (address 0), functions 6 and 16 | carried out, not answered |

Timing: a frame ends after 3.5 characters of silence (3.65 ms), and the answer starts right after
that. The old nodes answered after 1.5 characters.

The error counter (register 4) increases by one for each frame that starts with this node's
address and has a wrong checksum or is too short or too long, and for each exception.

### Differences from the old nodes on registers 0 to 4

| Old node | This firmware | Reason |
|---|---|---|
| Registers 5 and above: exception 2 | Registers 5 to 13 exist | Extensions go there |
| A range that starts inside the map and ends beyond it: exception 3 | Exception 2 | What the Modbus specification prescribes |
| The error counter also counted short frames addressed to other nodes, such as their exception responses | Counts only frames that start with its own address | A node's counter should describe its own traffic |
| Answered a broadcast "write single register" | Never answers a broadcast | Every node would answer at once |
| Wrote registers 1, 3 and 4 and overwrote them one loop pass later | Ignores the write | No value in between |

The controller's configuration needs no change: it reads and writes registers 0 and 2 with
functions 3 and 6.

## On the microcontroller

ATtiny1616 at 5 V, written in C++ directly on avr-libc. The plan named PlatformIO with
megaTinyCore and the ATtiny1614. The specification changed the chip to the ATtiny1616 for its pin
count. PlatformIO and megaTinyCore were dropped (owner, 2026-11-14): both ship a compiler from 2022
that exists for Intel only, and the firmware needs little from a framework. `src/main.cpp` sets up
the peripherals itself, in about 200 lines. Pins are those of the specification's
["Microcontroller and pin assignment"](valve-node-spec.md#microcontroller-and-pin-assignment).

| Point | How |
|---|---|
| Clock | 5 MHz: the internal 20 MHz oscillator divided by four |
| Serial port | USART0 in RS-485 mode: the USART drives XDIR on PB0 while it sends. Receiving and sending run through interrupts and two 64-byte buffers. The baud rate is corrected with the oscillator error that the factory stored in each chip |
| Time | Timer B0 interrupts once a millisecond; microseconds come from its counter |
| RXD | Internal pull-up, because the transceiver's receiver is off while the node sends |
| Outputs | Pins are inputs after reset, so the valves are closed; they are set low before they become outputs |
| Monitors | Internal pull-ups. The optocoupler pulls the pin low around each peak of the mains half-wave. The main loop samples the pin on every pass; voltage counts as present if a low level was seen within 100 ms (ten half-waves at 50 Hz) |
| Address switch | Internal pull-ups, read 2 ms after the pins are configured |
| Moisture | ADC0 input 1, 10 bit against the supply; one conversion a second, collected on a later pass of the main loop |
| Unused pins | PA3, PB1, PB4 and PB5 are inputs with pull-up |
| Watchdog | 2 s period, started by the WDTCFG fuse and locked. If a chip was flashed without its fuses, the firmware starts the watchdog itself; in both cases it sets the lock bit first thing, so nothing later can stop it. The main loop resets it on every pass |
| Brown-out reset | Highest level, 4.2 V nominal, set by fuse |
| Storage | Nothing is stored. The EEPROM is unused |

The main loop never waits. The build uses 3,176 of 16,384 bytes of flash and 319 of 2,048 bytes
of RAM.

Fuses are written by `make firmware-upload` and set in `firmware/valve-node/Makefile`: watchdog
2 s (`fuse0 = 0x09`), brown-out detector enabled at level 7 (`fuse1 = 0xE4`), 20 MHz oscillator
(`fuse2 = 0x02`). The others keep their factory values, which leave the UPDI pin as UPDI.

## Build, test, program

The firmware is built with avr-gcc 14 (avr-libc 2.2.1) and programmed with avrdude 8, both
native from Homebrew: `brew tap osx-cross/avr && brew install osx-cross/avr/avr-gcc@14 avrdude`.
Homebrew asks once to trust the two formulae from that tap (`avr-gcc@14`, `avr-binutils`). Tests,
simulator and test bench need only the computer's C++ compiler and Python.

| Command | Result |
|---|---|
| `make firmware` | `build/valve-node/firmware/valve-node.hex` |
| `make firmware-test` | Unit tests, then the bus test against the simulator |
| `make firmware-sim NODES=1,2,3,4 SPEED=60` | Simulated nodes on `/tmp/valve-node-bus` until Ctrl-C |
| `make firmware-bench` | The simulator with four nodes and a page at `http://127.0.0.1:8485/` that plays the controller: switch valves, stop the polling, speed up the nodes' clock, inject faults |
| `make firmware-upload PORT=<device>` | Fuses and firmware over UPDI |
| `make selftest` | Among the other cases: builds the simulator with a 10 min bus-loss timeout and expects the bus test to fail |

Programming: a USB serial adapter at 5 V with a resistor between its TX and RX (the
"SerialUPDI" wiring that avrdude's `serialupdi` programmer expects), RX to the UPDI pad of the three-pad programming header, plus 5 V and ground.
The node is programmed once per board, with the bus unplugged or powered from the adapter alone.

### Simulator

`make firmware-sim` starts the core as one node per entry in `NODES` on a pseudo-terminal, which
stands in for the RS485 cable. Any Modbus client can open it:

```bash
mbpoll -m rtu -b 9600 -P none -a 2 -0 -r 0 -c 14 -1 /tmp/valve-node-bus          # read all registers of node 2
mbpoll -m rtu -b 9600 -P none -a 2 -0 -r 2 -1 /tmp/valve-node-bus -- 65535      # open its valve 2, as ESPHome does
```

`SPEED` makes the nodes' millisecond clock run faster, so the 60 s timeout and the 120 min limit
can be watched in seconds; frame timing stays in real time. The simulator prints each valve that
opens or closes, with the reason. Faults for the monitor are set on its command line
(`--no-ac`, `--fault 1:2:open-wire`, `--fault 1:1:dead-triac`; see the head of `sim/sim.cpp`).

The simulator runs the firmware's logic, not the microcontroller. No simulator for the
tinyAVR 1-series was at hand, so everything in `src/main.cpp` is tested on the first board: clock,
pins, serial port, timer, ADC, watchdog and fuses.

### What the tests check

| Test | Checks |
|---|---|
| Unit tests (19) | Checksum against the documented frame; reset state; setpoints; one valve per node; function 16; read-only registers; every exception; wrong checksum; other addresses; broadcast; switch at 0; a frame longer than the buffer; bus-loss timeout to 10 ms; requests that do not count; run-time limit while the controller polls and repeats the command; all timers across a wrap of the 32-bit clocks; the monitor's four cases; diagnostic registers; LED patterns |
| Bus test (16) | The same behaviour seen from the controller's side of a serial line, with the example frames of `bus-protocol.md` byte for byte; the answer delay of at least 3.65 ms; four nodes on one line, each answering to its own address only; bus loss and run-time limit with the fast clock; monitor faults |

The bus test also runs against a board: `firmware/valve-node/bustest.py --port <device> --address <n>`
with a USB RS485 adapter. The five checks that need the simulator's fast clock or its injected
faults are skipped then. It opens and closes the valves of the node under test.

## Not tested yet

For the bring-up of the first board, in this order:

| Point | Why it is open |
|---|---|
| Clock and timer: the LED blinks at 1 Hz without a controller | `src/main.cpp` has never run; this is its first sign of life |
| The serial port in RS-485 mode: direction switching, no echo of the node's own answer, baud rate within tolerance | Runs only on the chip |
| Fuses: watchdog period and lock, brown-out level, oscillator | Written by the programmer; read them back once |
| A watchdog reset closes the valves and shows as 8 in register 12 | The firmware reads the reset flags first thing and clears them |
| Address switch polarity and order: switch 1 is the lowest bit, "on" is 1 | Follows from the schematic, not tried |
| Monitor levels: the pin goes low at each peak with the valve closed and stays high with the valve open | Depends on the optocoupler's current transfer and the internal pull-up (see [`valve-node-schematic.md`](valve-node-schematic.md), deviation 3). If the low pulse is too short for the main loop to catch, the pin gets a pin-change interrupt |
| Bus test against the board with the existing controller disconnected, then the node behind the existing controller | The controller's timing is not recorded ([`bus-protocol.md`](bus-protocol.md#open-points)) |
| LED patterns | Seen only as register logic so far |

## Open points

| Point | Needed for | Who, when |
|---|---|---|
| A UPDI adapter: USB serial adapter at 5 V and a resistor | Programming | Owner, before the boards arrive |
| The new registers are not read by the existing controller | Monitor and closing reason in Home Assistant | With the new controller's ESPHome configuration |
