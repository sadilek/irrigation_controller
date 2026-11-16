// Unit tests of the core with a clock the test controls: frame timing, timers, clock wrap.
// The bus test (bustest.py) covers the protocol end to end over a serial line.

#include <stdio.h>
#include <string.h>

// A minimal test frame: a failed check prints its place and marks the running test as failed.
static int failures;
#define CHECK(condition) \
  do { \
    if (!(condition)) { \
      printf("    %s:%d: %s\n", __FILE__, __LINE__, #condition); \
      failures++; \
    } \
  } while (0)
#define TEST_ASSERT_TRUE(c) CHECK(c)
#define TEST_ASSERT_FALSE(c) CHECK(!(c))
#define TEST_ASSERT_EQUAL(expected, actual) CHECK((long)(expected) == (long)(actual))
#define TEST_ASSERT_EQUAL_HEX8(expected, actual) TEST_ASSERT_EQUAL(expected, actual)
#define TEST_ASSERT_EQUAL_HEX16(expected, actual) TEST_ASSERT_EQUAL(expected, actual)

#include "valve_node.h"

using namespace valve_node;

namespace {

ValveNode node;
uint32_t ms;  // the test's clock; microseconds are derived from it and wrap on their own
uint8_t response[64];
uint8_t response_length;

uint32_t us() { return ms * 1000u; }

void advance(uint32_t milliseconds, bool ac = true) {
  // In steps, so that every monitor window gets samples, as on the board.
  while (milliseconds) {
    uint32_t step = milliseconds > 20 ? 20 : milliseconds;
    ms += step;
    milliseconds -= step;
    for (uint8_t i = 0; i < OUTPUTS; i++) node.monitor(i, ac && !node.driven(i));
    TEST_ASSERT_EQUAL(0, node.poll(ms, us()));
  }
}

// Sends a frame (checksum appended here) and returns the response length.
uint8_t request(const uint8_t* frame, uint8_t length, bool corrupt = false) {
  uint8_t buffer[80];
  memcpy(buffer, frame, length);
  uint16_t crc = crc16(buffer, length);
  buffer[length++] = (uint8_t)crc ^ (corrupt ? 0x55 : 0);
  buffer[length++] = (uint8_t)(crc >> 8);
  for (uint8_t i = 0; i < length; i++) node.receive(buffer[i], us());
  TEST_ASSERT_EQUAL(0, node.poll(ms, us() + FRAME_GAP_US - 1));  // not yet: 3.5 characters of silence
  ms += 4;
  response_length = node.poll(ms, us());
  memcpy(response, node.response(), response_length);
  if (response_length) TEST_ASSERT_EQUAL(0, crc16(response, response_length));
  return response_length;
}

uint8_t write_register(uint8_t address, uint16_t index, uint16_t value) {
  const uint8_t frame[] = {address, 6, (uint8_t)(index >> 8), (uint8_t)index, (uint8_t)(value >> 8), (uint8_t)value};
  return request(frame, sizeof(frame));
}

uint8_t read_registers(uint8_t address, uint16_t start, uint16_t count) {
  const uint8_t frame[] = {address, 3, (uint8_t)(start >> 8), (uint8_t)start, (uint8_t)(count >> 8), (uint8_t)count};
  return request(frame, sizeof(frame));
}

void start(uint8_t address, uint32_t at_ms) {
  ms = at_ms;
  node.begin(address, 0x01, ms);
}

}  // namespace

void setUp() { start(1, 1000); }

void test_crc_matches_documented_frame() {
  // docs/bus-protocol.md: "Read all registers of node 1" is 01 03 00 00 00 05 85 C9.
  const uint8_t frame[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x05};
  TEST_ASSERT_EQUAL_HEX16(0xC985, crc16(frame, sizeof(frame)));
}

void test_closed_after_reset() {
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_FALSE(node.driven(1));
  TEST_ASSERT_EQUAL(15, read_registers(1, 0, 5));
  for (uint8_t i = 3; i < 13; i++) TEST_ASSERT_EQUAL(0, response[i]);
}

void test_any_nonzero_value_opens_and_reads_back() {
  TEST_ASSERT_EQUAL(8, write_register(1, 0, 0xFFFF));
  TEST_ASSERT_TRUE(node.driven(0));
  TEST_ASSERT_EQUAL_HEX16(0xFFFF, node.reg(REG_VALVE1_SETPOINT));
  TEST_ASSERT_EQUAL(1, node.reg(REG_VALVE1_STATE));
  write_register(1, 0, 0);
  TEST_ASSERT_FALSE(node.driven(0));
  write_register(1, 2, 1);
  TEST_ASSERT_TRUE(node.driven(1));
  TEST_ASSERT_EQUAL(1, node.reg(REG_VALVE2_SETPOINT));
}

void test_opening_one_valve_closes_the_other() {
  write_register(1, 0, 1);
  write_register(1, 2, 1);
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_TRUE(node.driven(1));
  TEST_ASSERT_EQUAL(0, node.reg(REG_VALVE1_SETPOINT));
  TEST_ASSERT_EQUAL(CLOSED_BY_INTERLOCK, node.reg(REG_VALVE1_CLOSED_BY));
  write_register(1, 0, 1);  // opening again clears the reason
  TEST_ASSERT_EQUAL(CLOSED_BY_CONTROLLER, node.reg(REG_VALVE1_CLOSED_BY));
  TEST_ASSERT_EQUAL(CLOSED_BY_INTERLOCK, node.reg(REG_VALVE2_CLOSED_BY));
}

void test_write_multiple_opening_both_keeps_the_second() {
  const uint8_t frame[] = {1, 16, 0, 0, 0, 3, 6, 0, 1, 0, 9, 0, 1};
  TEST_ASSERT_EQUAL(8, request(frame, sizeof(frame)));
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_TRUE(node.driven(1));
  TEST_ASSERT_EQUAL(0, node.reg(REG_VALVE1_STATE));  // the write to register 1 had no effect
}

void test_other_registers_ignore_writes() {
  for (uint16_t index = 0; index < REG_COUNT; index++) {
    if (index == REG_VALVE1_SETPOINT || index == REG_VALVE2_SETPOINT) continue;
    uint16_t before = node.reg((uint8_t)index);
    TEST_ASSERT_EQUAL(8, write_register(1, index, 0x1234));
    TEST_ASSERT_EQUAL(before, node.reg((uint8_t)index));
  }
  TEST_ASSERT_EQUAL(0, node.reg(REG_ERRORS));
}

void test_exceptions() {
  const uint8_t unknown[] = {1, 4, 0, 0, 0, 1};
  TEST_ASSERT_EQUAL(5, request(unknown, sizeof(unknown)));
  TEST_ASSERT_EQUAL_HEX8(0x84, response[1]);
  TEST_ASSERT_EQUAL(1, response[2]);
  TEST_ASSERT_EQUAL(5, read_registers(1, REG_COUNT, 1));
  TEST_ASSERT_EQUAL(2, response[2]);
  TEST_ASSERT_EQUAL(5, read_registers(1, REG_COUNT - 1, 2));
  TEST_ASSERT_EQUAL(2, response[2]);
  TEST_ASSERT_EQUAL(5, read_registers(1, 0, 0));
  TEST_ASSERT_EQUAL(3, response[2]);
  TEST_ASSERT_EQUAL(5, write_register(1, REG_COUNT, 1));
  TEST_ASSERT_EQUAL(2, response[2]);
  const uint8_t bad_count[] = {1, 16, 0, 0, 0, 2, 2, 0, 1};
  TEST_ASSERT_EQUAL(5, request(bad_count, sizeof(bad_count)));
  TEST_ASSERT_EQUAL(3, response[2]);
  TEST_ASSERT_EQUAL(6, node.reg(REG_ERRORS));
  TEST_ASSERT_EQUAL(15 + 2 * (REG_COUNT - 5), read_registers(1, 0, REG_COUNT));  // the whole map in one read
}

void test_wrong_checksum_is_counted_and_not_answered() {
  const uint8_t frame[] = {1, 6, 0, 0, 0, 1};
  TEST_ASSERT_EQUAL(0, request(frame, sizeof(frame), true));
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_EQUAL(1, node.reg(REG_ERRORS));
}

void test_other_addresses_are_ignored() {
  TEST_ASSERT_EQUAL(0, write_register(2, 0, 1));
  const uint8_t frame[] = {2, 6, 0, 0, 0, 1};
  TEST_ASSERT_EQUAL(0, request(frame, sizeof(frame), true));
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_EQUAL(0, node.reg(REG_ERRORS));
}

void test_broadcast_writes_without_answer() {
  write_register(1, 0, 1);
  TEST_ASSERT_EQUAL(0, write_register(0, 0, 0));
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_EQUAL(0, read_registers(0, 0, 1));
}

void test_switch_position_zero_stays_off_the_bus() {
  start(0, 1000);
  TEST_ASSERT_EQUAL(0, write_register(0, 0, 1));
  TEST_ASSERT_EQUAL(0, write_register(1, 0, 1));
  TEST_ASSERT_FALSE(node.driven(0));
}

void test_frame_longer_than_the_buffer() {
  for (uint8_t i = 0; i < 100; i++) node.receive(1, us());
  ms += 4;
  TEST_ASSERT_EQUAL(0, node.poll(ms, us()));
  TEST_ASSERT_EQUAL(1, node.reg(REG_ERRORS));
  TEST_ASSERT_EQUAL(8, write_register(1, 0, 1));  // the next frame is read normally
}

void test_bus_loss_closes_after_60_s() {
  write_register(1, 0, 0xFFFF);
  advance(BUS_TIMEOUT_MS - 10);
  TEST_ASSERT_TRUE(node.driven(0));
  advance(10);
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_EQUAL(0, node.reg(REG_VALVE1_SETPOINT));
  TEST_ASSERT_EQUAL(CLOSED_BY_BUS_TIMEOUT, node.reg(REG_VALVE1_CLOSED_BY));
}

void test_requests_to_other_nodes_do_not_keep_a_valve_open() {
  write_register(1, 0, 1);
  for (uint8_t i = 0; i < 20; i++) {
    advance(5000);
    read_registers(2, 0, 1);
    const uint8_t unknown[] = {1, 4, 0, 0, 0, 1};  // answered with an exception: not a valid request
    request(unknown, sizeof(unknown));
  }
  TEST_ASSERT_FALSE(node.driven(0));
  TEST_ASSERT_EQUAL(CLOSED_BY_BUS_TIMEOUT, node.reg(REG_VALVE1_CLOSED_BY));
}

void test_run_time_limit_closes_after_120_min() {
  write_register(1, 2, 1);
  const uint32_t opened = ms;
  for (;;) {
    advance(5000);
    if (!node.driven(1)) break;
    read_registers(1, 0, 1);  // the controller keeps polling
    write_register(1, 2, 1);  // and even repeats the command, which must not extend the time
    TEST_ASSERT_TRUE(ms - opened < MAX_OPEN_MS + 10000);
  }
  TEST_ASSERT_TRUE(ms - opened >= MAX_OPEN_MS);
  TEST_ASSERT_EQUAL(CLOSED_BY_RUN_TIME, node.reg(REG_VALVE2_CLOSED_BY));
  TEST_ASSERT_EQUAL(120, node.reg(REG_UPTIME_MINUTES));
}

void test_timers_survive_a_wrapping_clock() {
  start(1, 0xFFFFFFFFu - 30000u);  // 30 s before the millisecond clock wraps
  write_register(1, 0, 1);
  advance(59000);
  TEST_ASSERT_TRUE(node.driven(0));
  TEST_ASSERT_EQUAL(8, write_register(1, 0, 1));  // frame timing across the wrap of both clocks
  advance(59000);
  TEST_ASSERT_TRUE(node.driven(0));
  advance(1000);
  TEST_ASSERT_FALSE(node.driven(0));
}

void test_monitor() {
  // Off, supply and solenoid present: voltage across the triac, no fault.
  advance(300);
  TEST_ASSERT_EQUAL(0, node.reg(REG_OUTPUT1_MONITOR));
  // On and conducting: no voltage, no fault.
  write_register(1, 0, 1);
  TEST_ASSERT_EQUAL(MONITOR_DRIVEN, node.reg(REG_OUTPUT1_MONITOR));
  advance(300);
  TEST_ASSERT_EQUAL(MONITOR_DRIVEN, node.reg(REG_OUTPUT1_MONITOR));
  // On, but voltage stays: the triac did not fire.
  for (uint8_t i = 0; i < 20; i++) {
    node.monitor(0, true);
    ms += 20;
    node.poll(ms, us());
  }
  TEST_ASSERT_EQUAL(MONITOR_DRIVEN | MONITOR_FAULT, node.reg(REG_OUTPUT1_MONITOR));
  // Off and no voltage: supply missing or wire open. Not reported before one window has passed.
  write_register(1, 0, 0);
  TEST_ASSERT_EQUAL(0, node.reg(REG_OUTPUT1_MONITOR));
  advance(300, false);
  TEST_ASSERT_EQUAL(MONITOR_FAULT, node.reg(REG_OUTPUT1_MONITOR));
  TEST_ASSERT_EQUAL(MONITOR_FAULT, node.reg(REG_OUTPUT2_MONITOR));
}

void test_diagnostic_registers() {
  start(7, 5000);
  TEST_ASSERT_EQUAL(FIRMWARE_VERSION, node.reg(REG_VERSION));
  TEST_ASSERT_EQUAL(7, node.reg(REG_ADDRESS));
  TEST_ASSERT_EQUAL(0, node.reg(REG_RESERVED));
  TEST_ASSERT_EQUAL(0x01, node.reg(REG_RESET_CAUSE));
  advance(185000);
  TEST_ASSERT_EQUAL(3, node.reg(REG_UPTIME_MINUTES));
}

void test_led() {
  start(0, 0);
  TEST_ASSERT_FALSE(node.led(50));  // no address: 5 Hz
  TEST_ASSERT_TRUE(node.led(150));
  start(1, 0);
  TEST_ASSERT_FALSE(node.led(400));  // no controller yet: 1 Hz
  TEST_ASSERT_TRUE(node.led(600));
  read_registers(1, 0, 1);
  TEST_ASSERT_TRUE(node.led(ms + 10));  // flicker for the answered request
  TEST_ASSERT_FALSE(node.led(ms + 600));  // then dark while all valves are closed
  write_register(1, 0, 1);
  TEST_ASSERT_TRUE(node.led(ms + 600));  // on while a valve is open
}

int main() {
  struct { const char* name; void (*run)(); } tests[] = {
    {"crc_matches_documented_frame", test_crc_matches_documented_frame},
    {"closed_after_reset", test_closed_after_reset},
    {"any_nonzero_value_opens_and_reads_back", test_any_nonzero_value_opens_and_reads_back},
    {"opening_one_valve_closes_the_other", test_opening_one_valve_closes_the_other},
    {"write_multiple_opening_both_keeps_the_second", test_write_multiple_opening_both_keeps_the_second},
    {"other_registers_ignore_writes", test_other_registers_ignore_writes},
    {"exceptions", test_exceptions},
    {"wrong_checksum_is_counted_and_not_answered", test_wrong_checksum_is_counted_and_not_answered},
    {"other_addresses_are_ignored", test_other_addresses_are_ignored},
    {"broadcast_writes_without_answer", test_broadcast_writes_without_answer},
    {"switch_position_zero_stays_off_the_bus", test_switch_position_zero_stays_off_the_bus},
    {"frame_longer_than_the_buffer", test_frame_longer_than_the_buffer},
    {"bus_loss_closes_after_60_s", test_bus_loss_closes_after_60_s},
    {"requests_to_other_nodes_do_not_keep_a_valve_open", test_requests_to_other_nodes_do_not_keep_a_valve_open},
    {"run_time_limit_closes_after_120_min", test_run_time_limit_closes_after_120_min},
    {"timers_survive_a_wrapping_clock", test_timers_survive_a_wrapping_clock},
    {"monitor", test_monitor},
    {"diagnostic_registers", test_diagnostic_registers},
    {"led", test_led},
  };
  int failed = 0;
  for (const auto& test : tests) {
    int before = failures;
    setUp();
    test.run();
    bool ok = failures == before;
    printf("%s  %s\n", ok ? "ok  " : "FAIL", test.name);
    if (!ok) failed++;
  }
  int count = (int)(sizeof(tests) / sizeof(tests[0]));
  printf("%d of %d unit tests passed\n", count - failed, count);
  return failed ? 1 : 0;
}
