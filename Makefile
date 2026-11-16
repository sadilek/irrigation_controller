# One command per output. `make help` lists them; docs/toolchain.md explains the chain.
# Usage: make <target> [BOARD=<directory under boards/>]

BOARD ?= throwaway
# Exact Zener toolchain. The `pcb-version` lane in pcb.toml floats to the newest 0.4.x release;
# this pin keeps builds reproducible. Raise it deliberately and rerun `make all`.
ZENER ?= 0.4.101

SRC := boards/$(BOARD)
EDA := $(SRC)/eda
OUT := build/$(BOARD)
PCB := $(abspath .tools/bin/pcb) +$(ZENER)
KICAD ?= /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
# kicad-cli prints dozens of Fontconfig warnings on stderr; its real messages go to stdout.
QUIET := 2>/dev/null
KIPY := tools/kipython
# KiCad's Python prints harmless SWIG and wxWidgets chatter; drop it, keep the exit status.
FILTER := 2>&1 | grep -v -e 'memory leak' -e 'create wxApp' ; exit $${PIPESTATUS[0]}

SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
.PHONY: help setup check apply arrange bom erc schematic layout drc render plots fab enclosure collide all verify selftest clean

help: ## List the targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 12

setup: ## Install the pinned toolchain into .tools/ and .venv/
	scripts/setup.sh

check: ## Compile the Zener source: connectivity, typed nets, voltage checks
	cd $(SRC) && $(PCB) build $(BOARD).zen

apply: check ## Generate/update the KiCad schematic and board from the Zener source, then arrange the schematic
	@# A schematic.py redraws the whole sheet, so Zener starts from an empty one: its incremental
	@# update of an arranged schematic left a library symbol renamed and its instances dangling.
	@if [ -f $(SRC)/schematic.py ]; then rm -f $(EDA)/$(BOARD).kicad_sch; fi
	cd $(SRC) && $(PCB) apply --no-open $(BOARD).zen
	@$(MAKE) --no-print-directory arrange BOARD=$(BOARD)

arrange: ## Arrange the schematic from boards/<board>/schematic.py (if the board has one), then compare it with the source
	@if [ -f $(SRC)/schematic.py ]; then uv run python $(SRC)/schematic.py && cd $(SRC) && $(PCB) build -D warnings $(BOARD).zen; fi

erc: ## KiCad electrical rules check on the generated schematic -> build/<board>/erc.rpt
	@mkdir -p $(OUT)
	$(KICAD) sch erc --severity-all --exit-code-violations -o $(OUT)/erc.rpt $(EDA)/$(BOARD).kicad_sch $(QUIET)

schematic: ## Schematic as PDF -> build/<board>/<board>-schematic.pdf
	@mkdir -p $(OUT)
	$(KICAD) sch export pdf -o $(OUT)/$(BOARD)-schematic.pdf $(EDA)/$(BOARD).kicad_sch $(QUIET)

bom: ## Review BOM with LCSC numbers, assembly side and unpopulated footprints -> build/<board>/<board>-bom.csv, .md
	@$(KIPY) tools/bom.py $(BOARD) $(FILTER)

layout: ## Outline, placement, zones and routing from boards/<board>/layout.py
	@$(KIPY) $(SRC)/layout.py $(FILTER)

drc: ## Fill zones, then KiCad design rules check -> build/<board>/drc.rpt
	@mkdir -p $(OUT)
	$(KICAD) pcb drc --refill-zones --save-board --severity-all --exit-code-violations -o $(OUT)/drc.rpt $(EDA)/$(BOARD).kicad_pcb $(QUIET)

render: ## 3D renders of the board: top, bottom, at an angle -> build/<board>/render-*.png
	@mkdir -p $(OUT)
	$(KICAD) pcb render --side top --quality high -w 1600 -h 1000 -o $(OUT)/render-top.png $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	$(KICAD) pcb render --side bottom --quality high -w 1600 -h 1000 -o $(OUT)/render-bottom.png $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	$(KICAD) pcb render --side top --rotate "-40,0,-20" --perspective --quality high -w 1600 -h 1000 -o $(OUT)/render-angle.png $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)

PLOT := $(KICAD) pcb export svg --mode-single --page-size-mode 2 --exclude-drawing-sheet
plots: ## Flat drawings: copper per side, copper by net class, assembly drawing, 1:1 print -> build/<board>/plots/
	@mkdir -p $(OUT)/plots
	$(PLOT) --layers F.Cu,F.SilkS,Edge.Cuts -o $(OUT)/plots/copper-top.svg $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	$(PLOT) --layers B.Cu,B.SilkS,Edge.Cuts --mirror -o $(OUT)/plots/copper-bottom.svg $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	$(PLOT) --layers F.Fab,Edge.Cuts --black-and-white --sp -o $(OUT)/plots/assembly-top.svg $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	$(KICAD) pcb export pdf --mode-single --scale 1 --black-and-white --layers Edge.Cuts,F.Fab,F.SilkS,Cmts.User -o $(OUT)/plots/$(BOARD)-1to1.pdf $(EDA)/$(BOARD).kicad_pcb >/dev/null $(QUIET)
	@$(KIPY) tools/classmap.py $(BOARD) $(FILTER)

fab: ## Gerbers + drill (zip), JLCPCB BOM and placement file, board STEP -> build/<board>/fab/
	@$(KIPY) tools/fab.py $(BOARD) $(FILTER)

enclosure: ## Enclosure parts as STEP and STL (valve node: also pictures) -> build/<board>/enclosure/, print/, views/
	uv run python $(SRC)/enclosure.py

collide: ## Collision check: board STEP against the enclosure parts
	uv run python tools/collide.py $(BOARD)

all: apply erc schematic layout drc render plots fab enclosure collide ## The whole chain, source to checked outputs

verify: check erc ## All checks without modifying committed files (zones as last filled by `make drc`)
	$(KICAD) pcb drc --severity-all --exit-code-violations -o $(OUT)/drc.rpt $(EDA)/$(BOARD).kicad_pcb $(QUIET)
	@$(MAKE) --no-print-directory fab enclosure collide BOARD=$(BOARD)

selftest: ## Prove the checks can fail: a lowered lid (both enclosures), a misplaced programming plug, board supports without pin pockets, a changed schematic, a logic track near 24 VAC
	uv run python boards/throwaway/enclosure.py --lid-drop 6 >/dev/null
	@if uv run python tools/collide.py throwaway >/dev/null; then echo "selftest: collision NOT detected"; exit 1; else echo "selftest: collision detected as expected"; fi
	uv run python boards/throwaway/enclosure.py >/dev/null
	uv run python boards/valve-node/enclosure.py --no-views --lid-drop 8 >/dev/null
	@if uv run python tools/collide.py valve-node >/dev/null; then echo "selftest: valve node collision NOT detected"; exit 1; else echo "selftest: valve node collision detected as expected"; fi
	uv run python boards/valve-node/enclosure.py --no-views --updi-shift 1.27 >/dev/null
	@if uv run python tools/collide.py valve-node >/dev/null; then echo "selftest: UPDI plug between its pins NOT detected"; exit 1; else echo "selftest: UPDI plug between its pins detected as expected"; fi
	uv run python boards/valve-node/enclosure.py --no-views --no-pockets >/dev/null
	@if uv run python tools/collide.py valve-node >/dev/null; then echo "selftest: board support on the pins NOT detected"; exit 1; else echo "selftest: board support on the pins detected as expected"; fi
	uv run python boards/valve-node/enclosure.py --no-views >/dev/null
	@tools/selftest-schematic.sh valve-node $(PCB)
	@# A ground track 2.5 mm from the 24 VAC jumper pads, one under an optocoupler, one under a screw head.
	@$(KIPY) tools/selftest-drc.py valve-node GND F.Cu 60.0 31.0 60.0 33.0 "24 VAC to logic" $(FILTER)
	@$(KIPY) tools/selftest-drc.py valve-node GND B.Cu 62.0 10.0 66.0 10.0 "no copper under the optocouplers" $(FILTER)
	@$(KIPY) tools/selftest-drc.py valve-node GND F.Cu 6.5 2.0 6.5 6.0 "screw heads and standoffs" $(FILTER)

clean: ## Remove generated outputs
	rm -rf build
