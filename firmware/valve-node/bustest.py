#!/usr/bin/env python3
"""Bus test for the valve node: plays the controller on a serial line and checks every answer.

Without arguments it starts the simulator (sim/sim.cpp; `make firmware-test` builds it) and
tests the firmware core on a pseudo-terminal. With --port it tests a real node through a USB
RS485 adapter; the checks that need the simulator's fast clock or its injected faults are skipped.

    bustest.py                                  # against the simulator
    bustest.py --port /dev/cu.usbserial-XXXX --address 1   # against a board

Only the standard library is used. The expected behaviour is docs/valve-node-firmware.md.
"""

import argparse
import os
import select
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIMULATOR = HERE.parent.parent / "build/valve-node/firmware/sim"
SIM_PORT = "/tmp/valve-node-bustest"
REG_COUNT = 14
VERSION = 0x0100


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return bytes([crc & 0xFF, crc >> 8])


class Bus:
    """A serial line at 9600 baud, 8N1."""

    def __init__(self, path: str):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[2] |= termios.CLOCAL | termios.CREAD
        attrs[4] = attrs[5] = termios.B9600
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        self.response_delay = None

    def close(self):
        os.close(self.fd)

    def raw(self, frame: bytes, timeout: float = 0.3, expect: int = 0) -> bytes:
        """Sends bytes as they are and returns what comes back until the line falls silent.

        With expect, it returns as soon as that many bytes arrived, without waiting for silence.
        """
        time.sleep(0.005)  # more than 3.5 characters since the last frame
        termios.tcflush(self.fd, termios.TCIFLUSH)
        os.write(self.fd, frame)
        sent = time.monotonic()
        received = b""
        deadline = sent + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self.fd], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                break
            if not received:
                self.response_delay = time.monotonic() - sent
            received += os.read(self.fd, 256)
            if expect and len(received) >= expect:
                break
            deadline = time.monotonic() + 0.02
        return received

    def request(self, payload: bytes, timeout: float = 0.3, expect: int = 0) -> bytes:
        """Sends address, function and data with a checksum; returns the response without checksum."""
        response = self.raw(payload + crc16(payload), timeout, expect)
        if not response:
            return b""
        assert crc16(response[:-2]) == response[-2:], f"checksum of response {response.hex(' ')}"
        return response[:-2]

    def read(self, address: int, start: int, count: int = 1, fast: bool = False) -> list:
        """fast: do not wait for silence after the answer (the test bench at a fast node clock)."""
        payload = bytes([address, 3, start >> 8, start & 0xFF, count >> 8, count & 0xFF])
        response = self.request(payload, expect=5 + 2 * count if fast else 0)
        assert response[:3] == bytes([address, 3, 2 * count]), f"read response {response.hex(' ')}"
        return [response[3 + 2 * i] << 8 | response[4 + 2 * i] for i in range(count)]

    def write(self, address: int, register: int, value: int) -> bytes:
        payload = bytes([address, 6, register >> 8, register & 0xFF, value >> 8, value & 0xFF])
        response = self.request(payload)
        if address:
            assert response == payload, f"write response {response.hex(' ')}"
        return response


class Simulator:
    def __init__(self, *args: str):
        if not SIMULATOR.exists():
            sys.exit(f"{SIMULATOR} is missing: run `make firmware-test`, which builds it")
        if os.path.lexists(SIM_PORT):
            os.unlink(SIM_PORT)
        self.process = subprocess.Popen([str(SIMULATOR), "--port", SIM_PORT, *args], stdout=subprocess.DEVNULL)
        for _ in range(200):
            if os.path.lexists(SIM_PORT):
                break
            time.sleep(0.01)
        self.bus = Bus(SIM_PORT)

    def __enter__(self) -> Bus:
        return self.bus

    def __exit__(self, *_):
        self.bus.close()
        self.process.terminate()
        self.process.wait()


def equal(actual, expected, what: str):
    assert actual == expected, f"{what}: expected {expected!r}, got {actual!r}"


# --- Checks that run against the simulator and against a board ------------------------------------


def check_reset_state(bus: Bus, a: int):
    """After a reset both valves are closed and the old registers read zero."""
    bus.write(a, 0, 0)
    bus.write(a, 2, 0)
    registers = bus.read(a, 0, REG_COUNT)
    equal(registers[0:4], [0, 0, 0, 0], "registers 0 to 3")
    equal(registers[8], VERSION, "version")
    equal(registers[9], a, "address register")


def check_documented_frames(bus: Bus, a: int):
    """The example frames of docs/bus-protocol.md, byte for byte (written for node 1 or 2)."""
    if a == 2:
        on = bytes.fromhex("02 06 00 02 FF FF 29 89")  # open valve 2 of node 2, as ESPHome does
        off = bytes.fromhex("02 06 00 02 00 00 28 39")
        equal(bus.raw(on), on, "echo of the open command")
        equal(bus.read(a, 2, 2), [0xFFFF, 1], "valve 2 setpoint and state")
        equal(bus.raw(off), off, "echo of the close command")
    else:
        errors = bus.read(a, 4)[0]
        bus.write(a, 0, 1)
        response = bus.raw(bytes([a]) + bytes.fromhex("03 00 00 00 05") + crc16(bytes([a]) + bytes.fromhex("03 00 00 00 05")))
        expected = bytes([a]) + bytes.fromhex("03 0A 00 01 00 01 00 00 00 00") + bytes([errors >> 8, errors & 0xFF])
        equal(response, expected + crc16(expected), "read of registers 0 to 4 with valve 1 open")
        bus.write(a, 0, 0)
    if a == 1:
        equal(crc16(bytes.fromhex("01 03 00 00 00 05")), bytes.fromhex("85 C9"), "checksum of the documented request")


def check_setpoints(bus: Bus, a: int):
    """Any non-zero value opens, reads back as written, the state register follows."""
    for value in (1, 0xFFFF, 0x0100):
        bus.write(a, 0, value)
        equal(bus.read(a, 0, 2), [value, 1], f"valve 1 after writing {value}")
        bus.write(a, 0, 0)
        equal(bus.read(a, 0, 2), [0, 0], "valve 1 after writing 0")


def check_interlock(bus: Bus, a: int):
    """Opening one valve closes the node's other valve and says why."""
    bus.write(a, 0, 0xFFFF)
    bus.write(a, 2, 0xFFFF)
    equal(bus.read(a, 0, 4), [0, 0, 0xFFFF, 1], "after opening valve 2 while valve 1 was open")
    equal(bus.read(a, 10)[0], 3, "valve 1 closed by the interlock")
    bus.write(a, 0, 1)
    equal(bus.read(a, 0, 4), [1, 1, 0, 0], "after opening valve 1 while valve 2 was open")
    equal(bus.read(a, 10, 2), [0, 3], "closed-by registers")
    bus.write(a, 0, 0)


def check_write_multiple(bus: Bus, a: int):
    """Function 16; a request that opens both valves leaves the second one open."""
    payload = bytes([a, 16, 0, 0, 0, 3, 6, 0, 1, 0, 0, 0, 1])
    equal(bus.request(payload), payload[:6], "response to write multiple")
    equal(bus.read(a, 0, 4), [0, 0, 1, 1], "registers after opening both")
    payload = bytes([a, 16, 0, 0, 0, 3, 6, 0, 0, 0, 0, 0, 0])
    bus.request(payload)
    equal(bus.read(a, 0, 4), [0, 0, 0, 0], "registers after closing both")


def check_read_only_registers(bus: Bus, a: int):
    """Writes to every other register are accepted and change nothing."""
    before = bus.read(a, 0, REG_COUNT)
    for register in range(REG_COUNT):
        if register not in (0, 2):
            bus.write(a, register, 0x1234)
    after = bus.read(a, 0, REG_COUNT)
    after[13] = before[13]  # the uptime may have advanced
    equal(after, before, "registers after writing the read-only ones")


def check_exceptions(bus: Bus, a: int):
    """Unknown function, register outside the map, wrong count; each one counts as an error."""
    errors = bus.read(a, 4)[0]
    equal(bus.request(bytes([a, 4, 0, 0, 0, 1])), bytes([a, 0x84, 1]), "unknown function")
    equal(bus.request(bytes([a, 3, 0, REG_COUNT, 0, 1])), bytes([a, 0x83, 2]), "read behind the last register")
    equal(bus.request(bytes([a, 3, 0, REG_COUNT - 1, 0, 2])), bytes([a, 0x83, 2]), "read across the end")
    equal(bus.request(bytes([a, 3, 0, 0, 0, 0])), bytes([a, 0x83, 3]), "read of zero registers")
    equal(bus.request(bytes([a, 6, 0, REG_COUNT, 0, 1])), bytes([a, 0x86, 2]), "write behind the last register")
    equal(bus.read(a, 4)[0], errors + 5, "error counter")


def check_bad_frames(bus: Bus, a: int):
    """A wrong checksum is counted and not answered; another node's frames are neither."""
    errors = bus.read(a, 4)[0]
    frame = bytes([a, 6, 0, 0, 0, 1])
    equal(bus.raw(frame + b"\x00\x00"), b"", "answer to a frame with a wrong checksum")
    other = 14 if a != 14 else 13
    frame = bytes([other, 6, 0, 0, 0, 1])
    equal(bus.raw(frame + crc16(frame)), b"", "answer to another node's request")
    equal(bus.raw(frame + b"\x00\x00"), b"", "answer to another node's damaged request")
    equal(bus.read(a, 0, 5), [0, 0, 0, 0, errors + 1], "valves closed, one error counted")


def check_broadcast(bus: Bus, a: int):
    """Address 0 is written without an answer."""
    bus.write(a, 0, 1)
    equal(bus.write(0, 0, 0), b"", "answer to a broadcast")
    equal(bus.read(a, 0, 2), [0, 0], "valve 1 after a broadcast close")


def check_answer_delay(bus: Bus, a: int):
    """The answer starts no earlier than 3.5 characters after the request (3.65 ms)."""
    delays = []
    for _ in range(20):
        bus.read(a, 0, 5)
        delays.append(bus.response_delay)
    assert min(delays) >= 0.0036, f"fastest answer after {min(delays) * 1000:.2f} ms"
    assert min(delays) < 0.05, f"fastest answer after {min(delays) * 1000:.2f} ms"


def check_monitor_ok(bus: Bus, a: int):
    """With supply and solenoid present, neither state of output 1 reports a fault."""
    time.sleep(0.3)
    equal(bus.read(a, 5)[0], 0, "monitor of output 1, closed")
    bus.write(a, 0, 1)
    time.sleep(0.3)
    equal(bus.read(a, 5)[0], 1, "monitor of output 1, open")
    bus.write(a, 0, 0)


COMMON = [
    check_reset_state,
    check_documented_frames,
    check_setpoints,
    check_interlock,
    check_write_multiple,
    check_read_only_registers,
    check_exceptions,
    check_bad_frames,
    check_broadcast,
    check_answer_delay,
    check_monitor_ok,
]

# --- Checks that need the simulator ---------------------------------------------------------------


def sim_four_nodes():
    """Four nodes with one firmware on one cable: each answers to its own address only."""
    with Simulator("--nodes", "1,2,3,4") as bus:
        for a in (1, 2, 3, 4):
            equal(bus.read(a, 9)[0], a, f"address register of node {a}")
            check_documented_frames(bus, a)
        bus.write(2, 2, 0xFFFF)
        equal([bus.read(a, 0, 4) for a in (1, 2, 3, 4)], [[0] * 4, [0, 0, 0xFFFF, 1], [0] * 4, [0] * 4], "only node 2 opened")
        equal(bus.request(bytes([5, 3, 0, 0, 0, 1])), b"", "answer from an address nobody has")


def sim_switch_zero():
    """A node whose switch is at 0 never answers and never opens."""
    with Simulator("--nodes", "0") as bus:
        equal(bus.request(bytes([0, 6, 0, 0, 0, 1])), b"", "answer to a broadcast")
        equal(bus.request(bytes([1, 3, 0, 0, 0, 1])), b"", "answer to address 1")


def sim_bus_loss():
    """Polled every 5 s a valve stays open; 60 s after the last request it closes."""
    with Simulator("--speed", "60") as bus:  # one second here is one minute for the node
        bus.write(1, 0, 0xFFFF)
        for _ in range(30):  # 150 s for the node
            time.sleep(5 / 60)
            equal(bus.read(1, 0)[0], 0xFFFF, "valve 1 while the controller polls")
        time.sleep(0.9)  # 54 s of silence
        equal(bus.read(1, 0)[0], 0xFFFF, "valve 1 after 54 s of silence")
        time.sleep(1.1)  # 66 s of silence
        equal(bus.read(1, 0, 2), [0, 0], "valve 1 after 66 s of silence")
        equal(bus.read(1, 10)[0], 1, "closed by the bus-loss timeout")
        bus.write(1, 0, 0xFFFF)
        equal(bus.read(1, 0, 2) + bus.read(1, 10), [0xFFFF, 1, 0], "the valve opens again on the next command")


def sim_run_time():
    """A valve closes after 120 min although the controller keeps polling."""
    speed = 600
    with Simulator("--speed", str(speed)) as bus:
        bus.write(1, 2, 0xFFFF)
        opened = time.monotonic()
        minutes = 0.0
        while bus.read(1, 2)[0]:
            minutes = (time.monotonic() - opened) * speed / 60
            assert minutes < 125, "valve 2 still open after 125 min"
            time.sleep(0.02)
        closed = (time.monotonic() - opened) * speed / 60
        assert minutes > 115, f"valve 2 closed after {closed:.0f} min"
        equal(bus.read(1, 11)[0], 2, "closed by the run-time limit")
        assert 119 <= bus.read(1, 13)[0] <= 125, "uptime register"


def sim_monitor_faults():
    """The monitor reports a missing supply, an open wire and a triac that does not fire."""
    with Simulator("--no-ac") as bus:
        time.sleep(0.3)
        equal(bus.read(1, 5, 2), [2, 2], "monitors without 24 VAC")
    with Simulator("--fault", "1:2:open-wire", "--fault", "1:1:dead-triac") as bus:
        time.sleep(0.3)
        equal(bus.read(1, 5, 2), [0, 2], "monitors with an open wire on output 2")
        bus.write(1, 0, 1)
        time.sleep(0.3)
        equal(bus.read(1, 5)[0], 3, "monitor of output 1 with a triac that does not fire")


SIM_ONLY = [sim_four_nodes, sim_switch_zero, sim_bus_loss, sim_run_time, sim_monitor_faults]


def run(name: str, doc: str, check) -> bool:
    try:
        check()
    except AssertionError as error:
        print(f"FAIL  {doc}\n      {name}: {error}")
        return False
    print(f"ok    {doc}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", help="serial device of a USB RS485 adapter; default: start the simulator")
    parser.add_argument("--simulator", help="simulator binary (default: build/valve-node/firmware/sim)")
    parser.add_argument("--address", type=int, default=1, help="address of the node under test (default 1)")
    args = parser.parse_args()

    global SIMULATOR
    if args.simulator:
        SIMULATOR = Path(args.simulator).resolve()
    results = []
    if args.port:
        bus = Bus(args.port)
        for check in COMMON:
            results.append(run(check.__name__, check.__doc__, lambda: check(bus, args.address)))
        print(f"skipped: {len(SIM_ONLY)} checks that need the simulator")
    else:
        with Simulator("--nodes", str(args.address)) as bus:
            for check in COMMON:
                results.append(run(check.__name__, check.__doc__, lambda: check(bus, args.address)))
        for check in SIM_ONLY:
            results.append(run(check.__name__, check.__doc__, check))

    failed = results.count(False)
    print(f"{len(results) - failed} of {len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
