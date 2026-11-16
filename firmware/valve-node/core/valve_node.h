// Valve node core: Modbus RTU server, register map and valve logic.
//
// Plain C++ without any hardware access, so the same code runs on the ATtiny1616 (src/main.cpp)
// and in the simulator on a computer (sim/sim.cpp). Behaviour and register map are documented
// in docs/valve-node-firmware.md.
#pragma once

#include <stdint.h>

namespace valve_node {

const uint8_t OUTPUTS = 2;
const uint16_t FIRMWARE_VERSION = 0x0100;  // major in the high byte, minor in the low byte

// All valves close after this time without a valid request to this node.
// The build flag exists for `make selftest`, which proves that the bus test notices a wrong value.
#ifndef VALVE_NODE_BUS_TIMEOUT_MS
#define VALVE_NODE_BUS_TIMEOUT_MS 60000UL
#endif
const uint32_t BUS_TIMEOUT_MS = VALVE_NODE_BUS_TIMEOUT_MS;
// A valve closes after this time open, whatever the controller says.
const uint32_t MAX_OPEN_MS = 120UL * 60UL * 1000UL;
// A frame ends after 3.5 characters of silence: 35 bits at 9600 baud.
const uint32_t FRAME_GAP_US = 3646UL;
// The monitor optocoupler pulls its pin low around each peak of the mains half-wave, every 10 ms
// at 50 Hz. Voltage counts as present when a low level was seen within one window.
const uint16_t MONITOR_WINDOW_MS = 100;
const uint16_t LED_FLASH_MS = 50;

enum Register {
  REG_VALVE1_SETPOINT = 0,  // read/write: 0 closes, any other value opens
  REG_VALVE1_STATE = 1,     // 1 while output 1 is driven
  REG_VALVE2_SETPOINT = 2,
  REG_VALVE2_STATE = 3,
  REG_ERRORS = 4,           // communication errors since reset, wraps
  // Registers 0 to 4 are the map of the nodes this one replaces. New registers start here.
  REG_OUTPUT1_MONITOR = 5,  // bit 0: output driven, bit 1: fault (see MonitorBit)
  REG_OUTPUT2_MONITOR = 6,
  REG_RESERVED = 7,         // reads 0; was meant for the moisture input, which the board dropped
  REG_VERSION = 8,
  REG_ADDRESS = 9,          // address read from the switch at reset
  REG_VALVE1_CLOSED_BY = 10,  // why valve 1 closed last (see ClosedBy)
  REG_VALVE2_CLOSED_BY = 11,
  REG_RESET_CAUSE = 12,     // reset flags of the microcontroller (RSTCTRL.RSTFR)
  REG_UPTIME_MINUTES = 13,  // minutes since reset, stops at 65535
  REG_COUNT = 14
};

enum MonitorBit {
  MONITOR_DRIVEN = 1,
  // Driven and voltage across the triac: the triac did not fire.
  // Not driven and no voltage: 24 VAC missing, fuse tripped, wire or solenoid open, triac shorted.
  MONITOR_FAULT = 2
};

enum ClosedBy {
  CLOSED_BY_CONTROLLER = 0,  // also: never opened, or open right now
  CLOSED_BY_BUS_TIMEOUT = 1,
  CLOSED_BY_RUN_TIME = 2,
  CLOSED_BY_INTERLOCK = 3    // the node's other valve was opened
};

uint16_t crc16(const uint8_t* data, uint8_t length);

class ValveNode {
 public:
  // address: 1 to 15 from the switch. With address 0 the node stays off the bus.
  void begin(uint8_t address, uint8_t reset_cause, uint32_t now_ms);

  // One received byte. now_us is a free-running microsecond clock.
  void receive(uint8_t byte, uint32_t now_us);

  // Call on every pass of the main loop. Returns the length of a response to send, or 0.
  uint8_t poll(uint32_t now_ms, uint32_t now_us);
  const uint8_t* response() const { return tx_; }

  // Level of an output's monitor, sampled as often as possible: true while voltage lies across
  // the triac.
  void monitor(uint8_t output, bool voltage);

  bool driven(uint8_t output) const { return setpoint_[output] != 0; }
  bool led(uint32_t now_ms) const;
  uint16_t reg(uint8_t index) const;

 private:
  struct Output {
    uint32_t opened_ms;
    uint32_t window_ms;
    bool seen;     // voltage seen in the running window
    bool voltage;  // result of the last complete window
    bool valid;    // a window completed since the output last switched
    uint8_t closed_by;
  };

  uint8_t handle(uint8_t length);
  uint8_t exception(uint8_t code);
  uint8_t finish(uint8_t length);
  void write(uint16_t index, uint16_t value);
  void close(uint8_t output, uint8_t closed_by);
  void restart_monitor(uint8_t output);

  uint8_t rx_[64];
  uint8_t tx_[64];
  uint8_t rx_length_;
  bool rx_overflow_;
  uint32_t last_byte_us_;

  uint8_t address_;
  uint8_t reset_cause_;
  uint16_t setpoint_[OUTPUTS];
  Output output_[OUTPUTS];
  uint16_t errors_;
  uint16_t uptime_minutes_;
  uint32_t minute_ms_;
  uint32_t now_ms_;
  uint32_t last_request_ms_;
  bool bus_alive_;  // a valid request arrived within BUS_TIMEOUT_MS
};

}  // namespace valve_node
