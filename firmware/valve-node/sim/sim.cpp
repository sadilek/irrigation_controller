// Bus simulator: one or more valve nodes on a pseudo-terminal that stands in for the RS485 cable.
//
// Runs the firmware core (core/valve_node.cpp) on the computer, so a Modbus client (mbpoll, the bus
// test, later ESPHome through a serial adapter) can talk to nodes before a board exists. It does
// not simulate the microcontroller: pins, serial port set-up and fuses are tested on the board.
//
//   valve-node-sim [--port PATH] [--nodes 1,2,3,4] [--speed N] [--no-ac] [--fault ADDR:OUTPUT:KIND]
//
//   --port   path of the symbolic link to the serial device (default /tmp/valve-node-bus)
//   --nodes  switch settings of the nodes on the bus (default 1)
//   --speed  the nodes' millisecond clock runs N times faster: with 60, the 60 s bus-loss timeout
//            takes one second. Frame timing stays in real time.
//   --no-ac  the 24 VAC supply is missing
//   --fault  KIND open-wire: no solenoid on this output; KIND dead-triac: the output never conducts
//
// The same settings can be changed while it runs, one command per line on standard input:
//   speed N | ac on|off | fault ADDR OUTPUT open-wire|dead-triac|none

#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#include "valve_node.h"

using valve_node::OUTPUTS;
using valve_node::ValveNode;

namespace {

const int MAX_NODES = 15;

struct SimNode {
  ValveNode node;
  int address;
  bool open_wire[OUTPUTS];
  bool dead_triac[OUTPUTS];
  bool was_driven[OUTPUTS];
};

SimNode nodes[MAX_NODES];
int node_count = 0;
const char* port = "/tmp/valve-node-bus";
volatile sig_atomic_t stop = 0;

void on_signal(int) { stop = 1; }

uint64_t micros64() {
  timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

const char* closed_by(uint16_t code) {
  switch (code) {
    case valve_node::CLOSED_BY_BUS_TIMEOUT: return "bus-loss timeout";
    case valve_node::CLOSED_BY_RUN_TIME: return "run-time limit";
    case valve_node::CLOSED_BY_INTERLOCK: return "other valve opened";
  }
  return "controller";
}

SimNode* find(int address) {
  for (int i = 0; i < node_count; i++) {
    if (nodes[i].address == address) return &nodes[i];
  }
  return nullptr;
}

bool set_fault(int address, int output, const char* kind) {
  SimNode* sim = find(address);
  if (!sim || output < 1 || output > OUTPUTS) return false;
  bool open_wire = !strcmp(kind, "open-wire");
  bool dead_triac = !strcmp(kind, "dead-triac");
  if (!open_wire && !dead_triac && strcmp(kind, "none")) return false;
  sim->open_wire[output - 1] = open_wire;
  sim->dead_triac[output - 1] = dead_triac;
  return true;
}

void usage() {
  fprintf(stderr, "usage: valve-node-sim [--port PATH] [--nodes 1,2,3,4] [--speed N] [--no-ac] [--fault ADDR:OUTPUT:open-wire|dead-triac]\n");
  exit(2);
}

}  // namespace

int main(int argc, char** argv) {
  unsigned speed = 1;
  bool ac = true;
  const char* node_list = "1";
  const char* faults[32];
  int fault_count = 0;

  for (int i = 1; i < argc; i++) {
    bool has_value = i + 1 < argc;
    if (!strcmp(argv[i], "--port") && has_value) {
      port = argv[++i];
    } else if (!strcmp(argv[i], "--nodes") && has_value) {
      node_list = argv[++i];
    } else if (!strcmp(argv[i], "--speed") && has_value) {
      speed = (unsigned)atoi(argv[++i]);
    } else if (!strcmp(argv[i], "--no-ac")) {
      ac = false;
    } else if (!strcmp(argv[i], "--fault") && has_value && fault_count < 32) {
      faults[fault_count++] = argv[++i];
    } else {
      usage();
    }
  }
  if (speed < 1) usage();

  char* list = strdup(node_list);
  for (char* item = strtok(list, ","); item; item = strtok(nullptr, ",")) {
    int address = atoi(item);
    if (address < 0 || address > 15 || node_count == MAX_NODES) usage();
    nodes[node_count] = SimNode();
    nodes[node_count].address = address;
    node_count++;
  }
  for (int i = 0; i < fault_count; i++) {
    int address, output;
    char kind[16];
    if (sscanf(faults[i], "%d:%d:%15s", &address, &output, kind) != 3 || !set_fault(address, output, kind)) usage();
  }

  // The pseudo-terminal: clients open the slave side through the symbolic link. Keeping our own
  // descriptor on the slave lets clients come and go.
  int master = posix_openpt(O_RDWR | O_NOCTTY);
  if (master < 0 || grantpt(master) || unlockpt(master)) {
    perror("pseudo-terminal");
    return 1;
  }
  const char* slave_name = ptsname(master);
  int slave = open(slave_name, O_RDWR | O_NOCTTY);
  termios tio;
  if (slave < 0 || tcgetattr(slave, &tio)) {
    perror(slave_name);
    return 1;
  }
  cfmakeraw(&tio);
  tcsetattr(slave, TCSANOW, &tio);
  unlink(port);
  if (symlink(slave_name, port)) {
    perror(port);
    return 1;
  }
  signal(SIGINT, on_signal);
  signal(SIGTERM, on_signal);
  setvbuf(stdout, nullptr, _IOLBF, 0);

  const uint64_t start = micros64();
  uint64_t last = 0;
  double node_ms = 0;  // the nodes' millisecond clock, which runs `speed` times faster
  bool commands = true;
  for (int i = 0; i < node_count; i++) nodes[i].node.begin((uint8_t)nodes[i].address, 0x01 /* power-on */, 0);
  printf("bus: %s, nodes: %s, clock x%u%s\n", port, node_list, speed, ac ? "" : ", 24 VAC missing");

  while (!stop) {
    pollfd pfds[2] = {{master, POLLIN, 0}, {STDIN_FILENO, POLLIN, 0}};
    uint8_t buffer[256];
    ssize_t received = 0;
    if (poll(pfds, commands ? 2 : 1, 1) > 0) {
      if (pfds[0].revents & POLLIN) received = read(master, buffer, sizeof(buffer));
      if (commands && pfds[1].revents) {
        char line[256];
        ssize_t n = read(STDIN_FILENO, line, sizeof(line) - 1);
        if (n <= 0) commands = false;  // standard input closed: keep running
        line[n > 0 ? n : 0] = 0;
        for (char* command = strtok(line, "\n"); command; command = strtok(nullptr, "\n")) {
          int address, output;
          unsigned value;
          char word[16];
          if (sscanf(command, "speed %u", &value) == 1 && value >= 1) {
            speed = value;
          } else if (sscanf(command, "ac %15s", word) == 1) {
            ac = !strcmp(word, "on");
          } else if (sscanf(command, "fault %d %d %15s", &address, &output, word) != 3 || !set_fault(address, output, word)) {
            fprintf(stderr, "unknown command: %s\n", command);
          }
        }
      }
    }

    uint64_t now = micros64() - start;
    node_ms += (double)(now - last) / 1000.0 * speed;
    last = now;
    uint32_t now_us = (uint32_t)now;
    uint32_t now_ms = (uint32_t)(uint64_t)node_ms;

    for (int i = 0; i < node_count; i++) {
      SimNode& sim = nodes[i];
      for (ssize_t b = 0; b < received; b++) sim.node.receive(buffer[b], now_us);
      uint8_t length = sim.node.poll(now_ms, now_us);
      if (length && write(master, sim.node.response(), length) != length) perror("write");

      for (uint8_t out = 0; out < OUTPUTS; out++) {
        bool driven = sim.node.driven(out);
        // Voltage lies across the triac when the supply is there, the solenoid closes the circuit
        // and the triac does not conduct. The real signal pulses at 100 Hz; here it is a level.
        bool conducts = driven && !sim.dead_triac[out];
        sim.node.monitor(out, ac && !sim.open_wire[out] && !conducts);
        if (driven != sim.was_driven[out]) {
          sim.was_driven[out] = driven;
          double seconds = node_ms / 1000.0;
          if (driven) {
            printf("[%8.1f s] node %d: valve %d OPEN\n", seconds, sim.address, out + 1);
          } else {
            printf("[%8.1f s] node %d: valve %d closed by %s\n", seconds, sim.address, out + 1,
                   closed_by(sim.node.reg(valve_node::REG_VALVE1_CLOSED_BY + out)));
          }
        }
      }
    }
  }

  unlink(port);
  return 0;
}
