#include "valve_node.h"

namespace valve_node {

namespace {

const uint8_t READ_HOLDING_REGISTERS = 3;
const uint8_t WRITE_SINGLE_REGISTER = 6;
const uint8_t WRITE_MULTIPLE_REGISTERS = 16;

const uint8_t ILLEGAL_FUNCTION = 1;
const uint8_t ILLEGAL_DATA_ADDRESS = 2;
const uint8_t ILLEGAL_DATA_VALUE = 3;

uint16_t word(const uint8_t* p) { return (uint16_t)((uint16_t)p[0] << 8 | p[1]); }

}  // namespace

uint16_t crc16(const uint8_t* data, uint8_t length) {
  uint16_t crc = 0xFFFF;
  while (length--) {
    crc ^= *data++;
    for (uint8_t bit = 0; bit < 8; bit++) {
      crc = (crc & 1) ? (uint16_t)((crc >> 1) ^ 0xA001) : (uint16_t)(crc >> 1);
    }
  }
  return crc;
}

void ValveNode::begin(uint8_t address, uint8_t reset_cause, uint32_t now_ms) {
  address_ = address;
  reset_cause_ = reset_cause;
  rx_length_ = 0;
  rx_overflow_ = false;
  last_byte_us_ = 0;
  errors_ = 0;
  moisture_ = 0;
  uptime_minutes_ = 0;
  minute_ms_ = now_ms;
  now_ms_ = now_ms;
  last_request_ms_ = now_ms;
  bus_alive_ = false;
  for (uint8_t i = 0; i < OUTPUTS; i++) {
    setpoint_[i] = 0;
    output_[i].opened_ms = now_ms;
    output_[i].closed_by = CLOSED_BY_CONTROLLER;
    restart_monitor(i);
  }
}

void ValveNode::receive(uint8_t byte, uint32_t now_us) {
  last_byte_us_ = now_us;
  if (rx_length_ < sizeof(rx_)) {
    rx_[rx_length_++] = byte;
  } else {
    rx_overflow_ = true;
  }
}

uint8_t ValveNode::poll(uint32_t now_ms, uint32_t now_us) {
  now_ms_ = now_ms;

  // All differences are unsigned, so they stay correct when a clock wraps.
  if ((uint32_t)(now_ms - minute_ms_) >= 60000UL) {
    minute_ms_ += 60000UL;
    if (uptime_minutes_ != 0xFFFF) uptime_minutes_++;
  }

  if (bus_alive_ && (uint32_t)(now_ms - last_request_ms_) >= BUS_TIMEOUT_MS) {
    bus_alive_ = false;
    for (uint8_t i = 0; i < OUTPUTS; i++) close(i, CLOSED_BY_BUS_TIMEOUT);
  }

  for (uint8_t i = 0; i < OUTPUTS; i++) {
    Output& out = output_[i];
    if (driven(i) && (uint32_t)(now_ms - out.opened_ms) >= MAX_OPEN_MS) close(i, CLOSED_BY_RUN_TIME);
    if ((uint32_t)(now_ms - out.window_ms) >= MONITOR_WINDOW_MS) {
      out.voltage = out.seen;
      out.valid = true;
      out.seen = false;
      out.window_ms = now_ms;
    }
  }

  if (rx_length_ == 0 || (uint32_t)(now_us - last_byte_us_) < FRAME_GAP_US) return 0;
  uint8_t length = rx_length_;
  bool overflow = rx_overflow_;
  rx_length_ = 0;
  rx_overflow_ = false;

  if (address_ == 0) return 0;  // no valid address: stay off the bus
  bool broadcast = rx_[0] == 0;
  if (rx_[0] != address_ && !broadcast) return 0;
  if (overflow || length < 4 || crc16(rx_, length - 2) != (uint16_t)(rx_[length - 2] | (uint16_t)rx_[length - 1] << 8)) {
    errors_++;
    return 0;
  }

  uint8_t response = handle(length);
  if (tx_[1] & 0x80) {
    errors_++;
  } else if (!broadcast) {
    last_request_ms_ = now_ms;
    bus_alive_ = true;
  }
  return broadcast ? 0 : response;
}

// Handles a request with a correct checksum and builds the response in tx_.
uint8_t ValveNode::handle(uint8_t length) {
  const uint8_t function = rx_[1];
  const bool broadcast = rx_[0] == 0;
  tx_[0] = address_;
  tx_[1] = function;

  if (function == READ_HOLDING_REGISTERS && !broadcast) {
    if (length != 8) return exception(ILLEGAL_DATA_VALUE);
    uint16_t start = word(rx_ + 2);
    uint16_t count = word(rx_ + 4);
    if (count == 0 || count > 125) return exception(ILLEGAL_DATA_VALUE);
    if (start >= REG_COUNT || count > (uint16_t)(REG_COUNT - start)) return exception(ILLEGAL_DATA_ADDRESS);
    tx_[2] = (uint8_t)(count * 2);
    uint8_t n = 3;
    for (uint16_t i = 0; i < count; i++) {
      uint16_t value = reg((uint8_t)(start + i));
      tx_[n++] = (uint8_t)(value >> 8);
      tx_[n++] = (uint8_t)value;
    }
    return finish(n);
  }

  if (function == WRITE_SINGLE_REGISTER) {
    if (length != 8) return exception(ILLEGAL_DATA_VALUE);
    uint16_t index = word(rx_ + 2);
    if (index >= REG_COUNT) return exception(ILLEGAL_DATA_ADDRESS);
    write(index, word(rx_ + 4));
    for (uint8_t i = 2; i < 6; i++) tx_[i] = rx_[i];
    return finish(6);
  }

  if (function == WRITE_MULTIPLE_REGISTERS) {
    if (length < 11) return exception(ILLEGAL_DATA_VALUE);
    uint16_t start = word(rx_ + 2);
    uint16_t count = word(rx_ + 4);
    if (count == 0 || count > 123 || rx_[6] != count * 2 || length != 9 + count * 2) return exception(ILLEGAL_DATA_VALUE);
    if (start >= REG_COUNT || count > (uint16_t)(REG_COUNT - start)) return exception(ILLEGAL_DATA_ADDRESS);
    // In register order: when one request opens both valves, the second one wins.
    for (uint16_t i = 0; i < count; i++) write(start + i, word(rx_ + 7 + 2 * i));
    for (uint8_t i = 2; i < 6; i++) tx_[i] = rx_[i];
    return finish(6);
  }

  return exception(ILLEGAL_FUNCTION);
}

uint8_t ValveNode::exception(uint8_t code) {
  tx_[1] |= 0x80;
  tx_[2] = code;
  return finish(3);
}

uint8_t ValveNode::finish(uint8_t length) {
  uint16_t crc = crc16(tx_, length);
  tx_[length++] = (uint8_t)crc;
  tx_[length++] = (uint8_t)(crc >> 8);
  return length;
}

// Only the two setpoints can be written. A write to any other register is accepted and has no
// effect, as on the nodes this one replaces.
void ValveNode::write(uint16_t index, uint16_t value) {
  uint8_t i;
  if (index == REG_VALVE1_SETPOINT) {
    i = 0;
  } else if (index == REG_VALVE2_SETPOINT) {
    i = 1;
  } else {
    return;
  }
  if (value == 0) {
    close(i, CLOSED_BY_CONTROLLER);
    return;
  }
  // One valve per node: transformer and cable carry one.
  for (uint8_t other = 0; other < OUTPUTS; other++) {
    if (other != i) close(other, CLOSED_BY_INTERLOCK);
  }
  if (!driven(i)) {
    // The run time counts from here. Writing the setpoint of an open valve again does not extend it.
    output_[i].opened_ms = now_ms_;
    output_[i].closed_by = CLOSED_BY_CONTROLLER;
    restart_monitor(i);
  }
  setpoint_[i] = value;  // reads back as written; the controller writes 0xFFFF
}

void ValveNode::close(uint8_t output, uint8_t closed_by) {
  if (!driven(output)) return;
  setpoint_[output] = 0;
  output_[output].closed_by = closed_by;
  restart_monitor(output);
}

void ValveNode::restart_monitor(uint8_t output) {
  output_[output].window_ms = now_ms_;
  output_[output].seen = false;
  output_[output].voltage = false;
  output_[output].valid = false;
}

void ValveNode::monitor(uint8_t output, bool voltage) {
  if (voltage) output_[output].seen = true;
}

uint16_t ValveNode::reg(uint8_t index) const {
  switch (index) {
    case REG_VALVE1_SETPOINT:
    case REG_VALVE2_SETPOINT:
      return setpoint_[index / 2];
    case REG_VALVE1_STATE:
    case REG_VALVE2_STATE:
      return driven(index / 2) ? 1 : 0;
    case REG_ERRORS:
      return errors_;
    case REG_OUTPUT1_MONITOR:
    case REG_OUTPUT2_MONITOR: {
      uint8_t i = index - REG_OUTPUT1_MONITOR;
      uint16_t value = driven(i) ? MONITOR_DRIVEN : 0;
      // Until the first window after switching is complete, no fault is reported.
      if (output_[i].valid && output_[i].voltage == driven(i)) value |= MONITOR_FAULT;
      return value;
    }
    case REG_MOISTURE:
      return moisture_;
    case REG_VERSION:
      return FIRMWARE_VERSION;
    case REG_ADDRESS:
      return address_;
    case REG_VALVE1_CLOSED_BY:
    case REG_VALVE2_CLOSED_BY:
      return output_[index - REG_VALVE1_CLOSED_BY].closed_by;
    case REG_RESET_CAUSE:
      return reset_cause_;
    case REG_UPTIME_MINUTES:
      return uptime_minutes_;
  }
  return 0;
}

// No valid address: fast blinking. No request from the controller for 60 s (or none yet): slow
// blinking. Otherwise on while a valve is open, with a short flicker for each answered request.
bool ValveNode::led(uint32_t now_ms) const {
  if (address_ == 0) return (now_ms / 100) & 1;
  if (!bus_alive_) return (now_ms / 500) & 1;
  bool open = false;
  for (uint8_t i = 0; i < OUTPUTS; i++) open = open || driven(i);
  bool flash = (uint32_t)(now_ms - last_request_ms_) < LED_FLASH_MS;
  return open != flash;
}

}  // namespace valve_node
