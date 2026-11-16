// Valve node on the ATtiny1616: clock, pins, serial port, timer and watchdog around the core
// in core/valve_node.cpp. Written directly on avr-libc; no framework.
// Pin assignment: docs/valve-node-spec.md, "Microcontroller and pin assignment".
// Register and bit names: Microchip ATtiny1614/1616/1617 datasheet, DS40002204A.

#include <avr/interrupt.h>
#include <avr/io.h>
#include <avr/wdt.h>
#include <util/atomic.h>
#include <util/delay.h>

#include "valve_node.h"

// Port A
static const uint8_t LED = PIN2_bm;
static const uint8_t DRIVE1 = PIN4_bm;
static const uint8_t MONITOR1 = PIN5_bm;
static const uint8_t DRIVE2 = PIN6_bm;
static const uint8_t MONITOR2 = PIN7_bm;
// Port B
static const uint8_t XDIR = PIN0_bm;
static const uint8_t TXD = PIN2_bm;
static const uint8_t RXD = PIN3_bm;
// Port C: address switch on pins 0 to 3, switch 1 on pin 0
static const uint8_t ADDRESS = PIN0_bm | PIN1_bm | PIN2_bm | PIN3_bm;

static valve_node::ValveNode node;

// --- Time: timer B0 overflows once a millisecond -------------------------------------------------

static const uint16_t TICKS_PER_MS = F_CPU / 1000;
static volatile uint32_t milliseconds;

ISR(TCB0_INT_vect) {
  milliseconds++;
  TCB0.INTFLAGS = TCB_CAPT_bm;
}

static uint32_t millis() {
  uint32_t ms;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { ms = milliseconds; }
  return ms;
}

static uint32_t micros() {
  uint32_t ms;
  uint16_t ticks;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    ms = milliseconds;
    ticks = TCB0.CNT;
    // The timer wrapped while interrupts were off: count that millisecond and read again.
    if (TCB0.INTFLAGS & TCB_CAPT_bm) {
      ms++;
      ticks = TCB0.CNT;
    }
  }
  return ms * 1000UL + ticks / (TICKS_PER_MS / 1000);
}

// --- Serial port: USART0 in RS-485 mode, both directions through interrupts ----------------------

static volatile uint8_t rx_buffer[64];  // size is a power of two
static volatile uint8_t rx_head, rx_tail;
static uint8_t tx_buffer[64];
static volatile uint8_t tx_length, tx_position;

ISR(USART0_RXC_vect) {
  uint8_t flags = USART0.RXDATAH;
  uint8_t byte = USART0.RXDATAL;
  // A byte with a framing error is kept: it damages the checksum, and the frame is then counted.
  (void)flags;
  uint8_t next = (uint8_t)(rx_head + 1) % sizeof(rx_buffer);
  if (next != rx_tail) {
    rx_buffer[rx_head] = byte;
    rx_head = next;
  }
}

ISR(USART0_DRE_vect) {
  USART0.TXDATAL = tx_buffer[tx_position++];
  if (tx_position == tx_length) USART0.CTRLA &= (uint8_t)~USART_DREIE_bm;
}

static void send(const uint8_t* data, uint8_t length) {
  for (uint8_t i = 0; i < length; i++) tx_buffer[i] = data[i];
  tx_position = 0;
  tx_length = length;
  USART0.CTRLA |= USART_DREIE_bm;
}

static void serial_begin() {
  // The factory measured this chip's oscillator error at 5 V, in steps of 1/1024; correct the
  // baud rate by it (datasheet 24.3.2.1 and the SIGROW description).
  int8_t error = (int8_t)SIGROW.OSC20ERR5V;
  uint32_t baud = (4UL * F_CPU + 9600 / 2) / 9600;  // 64 * F_CPU / (16 * baud rate)
  USART0.BAUD = (uint16_t)(baud * (uint32_t)(1024 + error) / 1024);
  USART0.CTRLC = USART_CHSIZE_8BIT_gc;  // asynchronous, no parity, one stop bit
  // The pull-up keeps RXD idle while the node sends: the transceiver's receiver is off then.
  PORTB.PIN3CTRL = PORT_PULLUPEN_bm;
  VPORTB.OUT |= TXD;
  VPORTB.OUT &= (uint8_t)~XDIR;
  VPORTB.DIR |= TXD | XDIR;
  VPORTB.DIR &= (uint8_t)~RXD;
  // RS-485 mode: the USART drives XDIR high from one bit before a frame until its last stop bit.
  USART0.CTRLA = USART_RXCIE_bm | USART_RS485_EXT_gc;
  USART0.CTRLB = USART_RXEN_bm | USART_TXEN_bm;
}

// --- Start-up ------------------------------------------------------------------------------------

// The WDTCFG fuse starts the watchdog at reset and locks it. If a chip was flashed without its
// fuses, start it here; either way lock it, so that nothing the firmware does later can stop it.
static void lock_watchdog() {
  if ((WDT.CTRLA & WDT_PERIOD_gm) == 0) _PROTECTED_WRITE(WDT.CTRLA, WDT_PERIOD_2KCLK_gc);
  while (WDT.STATUS & WDT_SYNCBUSY_bm) {}
  _PROTECTED_WRITE(WDT.STATUS, WDT_LOCK_bm);
}

int main() {
  lock_watchdog();
  uint8_t reset_cause = RSTCTRL.RSTFR;
  RSTCTRL.RSTFR = reset_cause;  // writing the flags back clears them

  // 5 MHz: the 20 MHz oscillator divided by four.
  _PROTECTED_WRITE(CLKCTRL.MCLKCTRLB, CLKCTRL_PDIV_4X_gc | CLKCTRL_PEN_bm);

  // Pins are inputs after reset, so the valves are closed. Low before they become outputs.
  VPORTA.OUT &= (uint8_t)~(DRIVE1 | DRIVE2 | LED);
  VPORTA.DIR |= DRIVE1 | DRIVE2 | LED;
  PORTA.PIN5CTRL = PORT_PULLUPEN_bm;  // monitors: the optocoupler pulls low
  PORTA.PIN7CTRL = PORT_PULLUPEN_bm;
  // Unused pins, on test pads: pull-up, so they do not float.
  PORTA.PIN1CTRL = PORT_PULLUPEN_bm;
  PORTA.PIN3CTRL = PORT_PULLUPEN_bm;
  PORTB.PIN1CTRL = PORT_PULLUPEN_bm;
  PORTB.PIN4CTRL = PORT_PULLUPEN_bm;
  PORTB.PIN5CTRL = PORT_PULLUPEN_bm;
  // Address switch: a closed switch pulls its pin to ground.
  PORTC.PIN0CTRL = PORT_PULLUPEN_bm;
  PORTC.PIN1CTRL = PORT_PULLUPEN_bm;
  PORTC.PIN2CTRL = PORT_PULLUPEN_bm;
  PORTC.PIN3CTRL = PORT_PULLUPEN_bm;

  // Switch 1 is the lowest bit. Read once, at reset.
  _delay_ms(2);
  uint8_t address = (uint8_t)(~VPORTC.IN) & ADDRESS;

  TCB0.CCMP = TICKS_PER_MS - 1;
  TCB0.INTCTRL = TCB_CAPT_bm;
  TCB0.CTRLA = TCB_CLKSEL_CLKDIV1_gc | TCB_ENABLE_bm;  // periodic interrupt mode is the default

  serial_begin();
  node.begin(address, reset_cause, 0);
  sei();

  for (;;) {
    wdt_reset();

    uint32_t now_ms = millis();
    while (rx_tail != rx_head) {
      uint8_t byte = rx_buffer[rx_tail];
      rx_tail = (uint8_t)(rx_tail + 1) % sizeof(rx_buffer);
      node.receive(byte, micros());
    }
    uint8_t length = node.poll(now_ms, micros());
    if (length) send(node.response(), length);

    uint8_t out = VPORTA.OUT & (uint8_t)~(DRIVE1 | DRIVE2 | LED);
    if (node.driven(0)) out |= DRIVE1;
    if (node.driven(1)) out |= DRIVE2;
    if (node.led(now_ms)) out |= LED;
    VPORTA.OUT = out;

    // The optocoupler pulls the pin low while voltage lies across the triac.
    uint8_t in = VPORTA.IN;
    node.monitor(0, !(in & MONITOR1));
    node.monitor(1, !(in & MONITOR2));
  }
}
