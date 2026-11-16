# Valve node firmware. Use the targets of the Makefile in the repository root (`make help` there);
# this file holds the rules. Documentation: docs/valve-node-firmware.md
#
# Needs avr-gcc with avr-libc 2.2 or newer and avrdude 7.1 or newer, both native from Homebrew:
#   brew tap osx-cross/avr && brew install osx-cross/avr/avr-gcc@14 avrdude

OUT ?= ../../build/valve-node/firmware
AVR_BIN ?= $(shell brew --prefix avr-gcc@14 2>/dev/null)/bin
AVR_BINUTILS ?= $(shell brew --prefix avr-binutils 2>/dev/null)/bin
AVRDUDE ?= avrdude
CXX ?= c++

MCU := attiny1616
F_CPU := 5000000UL
# Fuses: watchdog on with a 2 s period (and thereby locked); brown-out detector enabled at level 7
# (4.2 V); 20 MHz oscillator. All other fuses keep their factory values.
FUSES := -U fuse0:w:0x09:m -U fuse1:w:0xE4:m -U fuse2:w:0x02:m

CORE := core/valve_node.cpp core/valve_node.h
AVR_FLAGS := -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -std=gnu++17 -Wall -Wextra -Werror \
  -ffunction-sections -fdata-sections -fno-exceptions -fno-rtti -fno-threadsafe-statics -flto -Icore
HOST_FLAGS := -std=c++17 -O1 -Wall -Wextra -Werror -Icore

.PHONY: hex sim test selftest-sim upload
hex: $(OUT)/valve-node.hex
sim: $(OUT)/sim
selftest-sim: $(OUT)/sim-selftest

$(OUT)/valve-node.elf: src/main.cpp $(CORE)
	@mkdir -p $(OUT)
	@test -x $(AVR_BIN)/avr-g++ || { echo "avr-g++ not found: see the head of firmware/valve-node/Makefile"; exit 1; }
	$(AVR_BIN)/avr-g++ $(AVR_FLAGS) -Wl,--gc-sections -o $@ src/main.cpp core/valve_node.cpp

$(OUT)/valve-node.hex: $(OUT)/valve-node.elf
	$(AVR_BINUTILS)/avr-objcopy -O ihex -R .eeprom $< $@
	@$(AVR_BINUTILS)/avr-size $<

$(OUT)/sim: sim/sim.cpp $(CORE)
	@mkdir -p $(OUT)
	$(CXX) $(HOST_FLAGS) -o $@ sim/sim.cpp core/valve_node.cpp

# The simulator with a wrong bus-loss timeout. `make selftest` expects the bus test to fail on it.
$(OUT)/sim-selftest: sim/sim.cpp $(CORE)
	@mkdir -p $(OUT)
	$(CXX) $(HOST_FLAGS) -DVALVE_NODE_BUS_TIMEOUT_MS=600000UL -o $@ sim/sim.cpp core/valve_node.cpp

$(OUT)/test-node: test/test_node.cpp $(CORE)
	@mkdir -p $(OUT)
	$(CXX) $(HOST_FLAGS) -o $@ test/test_node.cpp core/valve_node.cpp

test: $(OUT)/test-node
	$(OUT)/test-node

upload: $(OUT)/valve-node.hex
	@if [ -z "$(PORT)" ]; then echo "usage: make firmware-upload PORT=/dev/cu.usbserial-..."; exit 2; fi
	$(AVRDUDE) -c serialupdi -p $(MCU) -P $(PORT) $(FUSES) -U flash:w:$<:i
