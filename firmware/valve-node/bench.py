#!/usr/bin/env python3
"""Test bench in the browser: simulated valve nodes on one bus, polled the way the controller does.

Starts the simulator (sim/sim.cpp) with four nodes, plays the controller on its serial line and
serves a page that shows every node's registers and lets you switch valves, stop the controller,
speed up the nodes' clock and inject faults. Everything shown is read over Modbus from the same
core that runs on the ATtiny1616. `make firmware-bench` builds the simulator and starts this.

Only the standard library is used.
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bustest import REG_COUNT, SIMULATOR, Bus

HERE = Path(__file__).resolve().parent
PORT = "/tmp/valve-node-bench"
NODES = [1, 2, 3, 4]
POLL_INTERVAL_S = 5.0  # in the nodes' time, as the existing controller polls


class Bench:
    def __init__(self):
        if not SIMULATOR.exists():
            sys.exit(f"{SIMULATOR} is missing: run `make firmware-bench`, which builds it")
        self.lock = threading.Lock()
        self.speed = 1
        self.polling = True
        self.ac = True
        self.faults = {}  # (address, output) -> kind
        self.registers = {a: None for a in NODES}
        self.events = []
        self.commands = []  # writes waiting for the controller thread
        self.sim = subprocess.Popen(
            [str(SIMULATOR), "--port", PORT, "--nodes", ",".join(map(str, NODES))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
        )
        self.sim.stdout.readline()  # the banner: the port exists now
        self.bus = Bus(PORT)
        threading.Thread(target=self.read_events, daemon=True).start()
        threading.Thread(target=self.controller, daemon=True).start()

    def simulator(self, command: str):
        self.sim.stdin.write(command + "\n")
        self.sim.stdin.flush()

    def read_events(self):
        for line in self.sim.stdout:
            with self.lock:
                self.events.append(line.strip())
                del self.events[:-40]

    def controller(self):
        """The only user of the serial line: pending writes first, then the polls that are due."""
        due = 0.0
        while True:
            with self.lock:
                commands, self.commands = self.commands, []
                polling, speed = self.polling, self.speed
            for address, register, value in commands:
                self.bus.write(address, register, value)
            if commands or (polling and time.monotonic() >= due):
                if not commands:
                    due = time.monotonic() + POLL_INTERVAL_S / speed
                for address in NODES:
                    try:
                        values = self.bus.read(address, 0, REG_COUNT, fast=True)
                    except (AssertionError, IndexError):
                        values = None
                    with self.lock:
                        self.registers[address] = values
            time.sleep(0.002)

    def state(self) -> dict:
        with self.lock:
            return {
                "speed": self.speed,
                "polling": self.polling,
                "ac": self.ac,
                "faults": [{"address": a, "output": o, "kind": k} for (a, o), k in self.faults.items()],
                "nodes": [{"address": a, "registers": self.registers[a]} for a in NODES],
                "events": self.events[-12:],
            }

    def act(self, action: dict):
        kind = action.get("action")
        with self.lock:
            if kind == "write":
                self.commands.append((int(action["address"]), int(action["register"]), int(action["value"])))
            elif kind == "polling":
                self.polling = bool(action["on"])
                self.events.append(f"controller: polling {'resumed' if self.polling else 'stopped'}")
            elif kind == "speed":
                self.speed = max(1, min(600, int(action["speed"])))
                self.simulator(f"speed {self.speed}")
            elif kind == "ac":
                self.ac = bool(action["on"])
                self.simulator(f"ac {'on' if self.ac else 'off'}")
                self.events.append(f"bench: 24 VAC {'on' if self.ac else 'off'}")
            elif kind == "fault":
                key = (int(action["address"]), int(action["output"]))
                fault = action["kind"] if action["kind"] in ("open-wire", "dead-triac") else "none"
                self.faults.pop(key, None)
                if fault != "none":
                    self.faults[key] = fault
                self.simulator(f"fault {key[0]} {key[1]} {fault}")
                self.events.append(f"bench: node {key[0]} output {key[1]}: {fault}")


def handler(bench: Bench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, body: bytes, content_type: str):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/state":
                self.send(json.dumps(bench.state()).encode(), "application/json")
            elif self.path == "/":
                self.send((HERE / "bench.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self.send_error(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            try:
                bench.act(json.loads(self.rfile.read(length)))
            except (ValueError, KeyError):
                self.send_error(400)
                return
            self.send(b"{}", "application/json")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--http-port", type=int, default=8485)
    args = parser.parse_args()
    bench = Bench()
    server = ThreadingHTTPServer(("127.0.0.1", args.http_port), handler(bench))
    print(f"test bench: http://127.0.0.1:{args.http_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        bench.sim.terminate()


if __name__ == "__main__":
    main()
