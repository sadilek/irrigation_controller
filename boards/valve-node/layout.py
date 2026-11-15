"""Placement and routing of the valve node. Run via `make layout BOARD=valve-node`.

The reasoning for every decision is in docs/valve-node-layout.md. In short:

  * Logic on the left, 24 VAC on the right. The four optocouplers stand in one column at x = 64
    and are the only parts that span the isolation gap.
  * The eight bus wires pass from jack to jack. Logic and the spare pair run in a band of lanes
    north of the jack pins, the 24 VAC pair south of them, +12 V on the other layer above it.
  * Everything that carries 24 VAC, the pass-through and the surge paths are drawn here by
    coordinates. What is left on the logic side is connected by the grid router
    (tools/gridroute.py), inside a region that ends before any of that copper.

Coordinates: millimetres from the board's top-left corner, x right, y down.
"""
import os

import pcbnew
from kilayout import Layout, write_rules

HERE = os.path.dirname(os.path.abspath(__file__))
F, B = pcbnew.F_Cu, pcbnew.B_Cu

# --- Rules --------------------------------------------------------------------------------------
# Net classes (docs/valve-node-spec.md, "Layout rules"). KiCad takes the larger clearance of two
# classes, so 0.5 mm holds inside class AC and between AC and the spare pair.
CLASSES = {
    "Power": {"clearance": 0.2, "track_width": 0.4},
    "AC": {"clearance": 0.5, "track_width": 0.8, "via_diameter": 0.8, "via_drill": 0.4},
    "Spare": {"clearance": 0.2, "track_width": 0.5, "via_diameter": 0.8, "via_drill": 0.4},
    "BusPower": {"clearance": 0.2, "track_width": 0.8, "via_diameter": 0.8, "via_drill": 0.4},
}
PATTERNS = [
    ("AC_*", "AC"),  # the 24 VAC pair and the fused valve common
    ("VALVE*", "AC"),
    ("OUT?.GATE", "AC"),
    ("OUT?.OPTO", "AC"),
    ("OUT?.SNUB", "AC"),
    ("OUT?.MON_LED", "AC"),
    ("OUT?.NC_U_DRV_NC5", "AC"),  # the optotriac's substrate pin, on the 24 VAC side of the part
    ("SPARE_?", "Spare"),  # carries 24 VAC once its two solder jumpers are bridged
    ("BUS_12V", "BusPower"),
    ("V12_F", "BusPower"),
    ("VIN", "Power"),
    ("+5V", "Power"),
    ("GND", "Power"),
]
RULES = """
(version 1)

# 24 VAC keeps 3 mm from everything that is not 24 VAC (docs/valve-node-spec.md, "Layout rules").
(rule "24 VAC to logic"
	(condition "A.NetClass == 'AC' && B.NetClass != 'AC' && B.NetClass != 'Spare'")
	(constraint clearance (min 3mm)))

# The spare pair can be bridged to the 24 VAC pair, so outside the pass-through it keeps the same
# distance. On the pass-through it runs between the logic lanes, as it does in the cable.
(rule "spare pair to logic"
	(condition "A.NetClass == 'Spare' && B.NetClass != 'AC' && B.NetClass != 'Spare'")
	(constraint clearance (min 3mm)))
(rule "spare pair to logic on the pass-through"
	(condition "A.NetClass == 'Spare' && B.NetClass != 'AC' && B.NetClass != 'Spare' && A.intersectsArea('passthrough')")
	(constraint clearance (min 0.2mm)))

# Inside a jack the pins are 1.02 mm apart: the one place where 24 VAC and logic are closer than
# 3 mm. Both items have to lie in the pin field for the exception to apply.
(rule "24 VAC to logic at the jack pins"
	(condition "A.NetClass == 'AC' && B.NetClass != 'AC' && B.NetClass != 'Spare' && A.intersectsArea('jack') && B.intersectsArea('jack')")
	(constraint clearance (min 0.4mm)))

# Keep-outs. KiCad 10.0.1 did not report a track inside a rule area that forbids tracks
# (`make selftest` found that), so each keep-out is also a rule of its own here.
(rule "no copper under the optocouplers"
	(condition "A.intersectsArea('isolation')")
	(constraint disallow track via zone))
(rule "screw heads and standoffs"
	(condition "A.intersectsArea('keepout-top') || A.intersectsArea('keepout-bottom')")
	(constraint disallow track via))

# An open solder jumper is two pads 0.3 mm apart, whatever nets they are on.
(rule "solder jumper gap"
	(condition "A.Type == 'Pad' && B.Type == 'Pad' && A.memberOfFootprint('JP*') && B.memberOfFootprint('JP*')")
	(constraint clearance (min 0.2mm)))
"""
write_rules(HERE, "valve-node", CLASSES, PATTERNS, RULES)

L = Layout(HERE, "valve-node")
L.clear()
L.outline_from_mech()
L.place_mounting_holes()
L.place_connectors()  # J_IN, J_OUT, J_VALVES, J_UPDI: positions shared with the enclosure (mech.json)

# --- Placement: 24 VAC side ---------------------------------------------------------------------
X_OPTO = 64.0  # the isolation gap runs along this line; logic pins at x - 4.76, 24 VAC pins at x + 4.76
X_AC = X_OPTO + 4.76
X_LOGIC = X_OPTO - 4.76
X_R = 71.1  # resistors: one column between the optocouplers and the valve terminal block
X_TRUNK = 72.3  # 24 VAC b on the bottom layer, from the OUT jack up to both outputs

# The valve terminal block stands at the far side of the board (mech.json), its wire openings
# towards the cable entries: the wires pass over output 1 and have 36 mm of free length.
# Output 2 sits in the strip behind the block, output 1 in front of it. In each pair of
# optocouplers the optotriac is the one next to its triac.
OPTO_Y = {"OUT2": {"U_DRV": 4.54, "U_MON": 11.58}, "OUT1": {"U_MON": 17.75, "U_DRV": 24.79}}
for out, rows in OPTO_Y.items():
    L.place(out + ".U_DRV", X_OPTO, rows["U_DRV"], rot=0, label=False)
    L.place(out + ".U_MON", X_OPTO, rows["U_MON"], rot=180, label=False)
    L.place(out + ".R_LED", 56.5, rows["U_DRV"] - 2.54, rot=0, label=False)
    L.place(out + ".R_MON", X_R, rows["U_MON"] + 2.18, rot=90, label=False)  # upper pad level with the monitor's pin
# Output 2: triac behind the block, leads towards the optotriac, snubber upright at its tab.
L.place("OUT2.R_GATE", X_R, 2.91, rot=90, label=False)
L.place("OUT2.R_GK", X_R, 6.25, rot=90, label=False)
L.place("OUT2.Q", 80.5, 3.9, rot=0, label=False)
L.place("OUT2.C_SNUB", 86.5, 2.25, rot=90, label=False)
L.place("OUT2.R_SNUB", 86.5, 5.75, rot=90, label=False)
# Output 1: triac in front of the block, tab towards it, leads towards the board edge; snubber and
# gate-to-A1 resistor in a column beside it. The triac is 2.3 mm high and the wire openings begin
# 1.4 mm above the board, so it keeps 8 mm from the block: a wire goes in straight.
L.place("OUT1.R_GATE", 71.85, 23.2, rot=180, label=False)
L.place("OUT1.Q", 77.3, 35.0, rot=90, label=False)
L.place("OUT1.R_SNUB", 82.0, 32.4, rot=270, label=False)
L.place("OUT1.C_SNUB", 82.0, 35.95, rot=270, label=False)
L.place("OUT1.R_GK", 82.0, 39.3, rot=90, label=False)

# 24 VAC protection, right where the pair leaves the OUT jack.
L.place("D4", 63.0, 39.5, rot=90, label=False)
L.place("F2", 68.5, 40.0, rot=0, label=False)
L.place("JP_SPARE_2", 63.0, 32.4, rot=270, label=False)
L.place("JP_SPARE_1", 67.5, 35.5, rot=270, label=False)

# --- Placement: bus protection between the jacks -------------------------------------------------
L.place("D3", 32.0, 25.0, rot=90, label=False)
L.place("D1", 33.0, 31.0, rot=0, label=False)
L.place("F1", 36.0, 36.5, rot=90, label=False)
L.place("D2", 40.0, 32.0, rot=270, label=False)

# --- Placement: logic ---------------------------------------------------------------------------
# Supply: series diode D2 (between the jacks), input capacitor, regulator, output capacitor.
L.place("C_VIN", 38.5, 26.2, rot=180, label=False)
L.place("U_REG", 43.0, 21.6, rot=90, label=False)
L.place("C_5V", 48.0, 24.6, rot=0, label=False)
# Microcontroller: outputs and monitors leave towards the optocouplers, the UART towards the transceiver.
L.place("U_MCU", 48.5, 8.5, rot=180, label=False)
L.place("C_MCU", 53.0, 8.1, rot=270, label=False)
L.place("SW_ADDR", 40.5, 13.4, rot=180, label=False)
L.place("R_LED", 53.2, 17.9, rot=0, label=False)
L.place("D_STATUS", 56.2, 17.9, rot=180, label=False)
# RS485: transceiver; the pair comes straight up from the TVS at the lanes.
L.place("U_RS485", 37.9, 6.4, rot=180, label=False)
L.place("C_RS485", 33.0, 6.4, rot=90, label=False)
L.place("R_XDIR", 43.8, 4.6, rot=0, label=False)
# Test pads: rails, and the five unused pins next to the microcontroller.
L.place("TP_5V", 52.5, 21.0, label=False)
L.place("TP_GND", 52.5, 24.6, label=False)
L.place("TP_VIN", 37.0, 22.6, label=False)
L.place("TP_PB4", 47.0, 2.6, label=False)
L.place("TP_PB5", 49.6, 2.6, label=False)
L.place("TP_PB1", 43.4, 8.0, label=False)
L.place("TP_PA3", 54.0, 5.2, label=False)
L.place("TP_PA1", 55.2, 10.4, label=False)
L.check_all_placed()

# --- Silkscreen ---------------------------------------------------------------------------------
# Reference designators are hidden (60 parts on this board leave no room for them; the assembly
# drawing has them). What is printed is what a person with the board in hand needs.
S = pcbnew.B_SilkS
L.text("BUS IN", 17.0, 25.4, 1.2)
L.text("24VAC! NO ETHERNET", 17.0, 27.4, 0.8)
L.text("BUS OUT", 51.0, 27.5, 1.0)
valve_pin_x = {n: L.pad("J_VALVES", n)[0] for n in (1, 2, 3, 4)}
for n, label in ((1, "V1"), (2, "C"), (3, "V2"), (4, "C")):  # in front of each wire opening of the valve terminal block
    L.text(label, valve_pin_x[n], 22.85, 0.8)
L.text("SPARE", 66.9, 32.9, 0.8)
L.text("ADDR", 40.5, 18.1, 0.8)
for label, x in (("UPDI", 49.5), ("5V", 52.04), ("GND", 54.58)):
    L.text(label, x, 16.1, 0.8)
for label, name, dx, dy in (("5V", "TP_5V", 0, -1.5), ("GND", "TP_GND", 2.2, 0), ("VIN", "TP_VIN", -2.2, 0), ("PB4", "TP_PB4", -2.4, 0),
                            ("PB5", "TP_PB5", 2.4, 0), ("PB1", "TP_PB1", 0, -1.6), ("PA3", "TP_PA3", 0, -1.5), ("PA1", "TP_PA1", -2.1, 0)):
    x, y = L.pad(name, 1)
    L.text(label, x + dx, y + dy, 0.8)
L.text("VALVE NODE", 14.0, 11.0, 1.5)
L.text("rev A", 14.0, 13.6, 1.0)
L.text("JLCJLCJLCJLC", 18.0, 12.0, 1.0, layer=S)  # where JLCPCB may print its order number
L.ruler(23.0, 50.0)

# --- Areas --------------------------------------------------------------------------------------
W, H = L.mech["board"]["width"], L.mech["board"]["height"]


def rect(x1, y1, x2, y2):
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


# No copper on either layer under the optocouplers, between their pin rows.
L.rule_area("isolation", [F, B], rect(X_LOGIC + 1.36, -1, X_AC - 1.36, 29.0))
# Named areas the custom rules refer to; they forbid nothing themselves.
JACK_Y = (33.5, 42.2)
L.rule_area("jack", [F, B], rect(12.3, JACK_Y[0], 22.9, JACK_Y[1]), tracks=False, vias=False, pours=False)
L.rule_area("jack", [F, B], rect(46.3, JACK_Y[0], 56.4, JACK_Y[1]), tracks=False, vias=False, pours=False)
L.rule_area("passthrough", [F, B], rect(12.0, 26.3, 52.3, 37.4), tracks=False, vias=False, pours=False)
L.keepouts_from_mech()  # screw heads on top, standoffs below

# --- Bus pass-through ---------------------------------------------------------------------------
p = {n: L.pad("J_IN", n) for n in range(1, 9)}  # 1 AC_A, 2 AC_B, 3 +12 V, 4 spare 1, 5 spare 2, 6 GND, 7 B, 8 A
q = {n: L.pad("J_OUT", n) for n in range(1, 9)}
SQUEEZE_Y = 33.4  # north of this a track is clear of the jack's pad rows
IN_EDGE, OUT_EDGE = 23.2, 56.7  # where a 24 VAC track leaves the pin field of a jack ("jack" areas)
PASS_EDGE = 53.0  # where the spare pair leaves the pass-through area

# North of the pins, bottom layer: one lane per wire, nested so that nothing crosses at the IN jack.
# At the OUT jack each lane ends in a via and drops to its pin on the top layer. The two pins of
# the inner row (B, spare 2) pass between two pads of the outer row with a 0.2 mm track.
LANE = {"BUS_A": 26.9, "BUS_B": 27.6, "GND": 28.6, "SPARE_2": 29.9, "SPARE_1": 31.0}
for net, pin, width, inner_row in (("BUS_A", 8, 0.3, False), ("BUS_B", 7, 0.3, True), ("GND", 6, 0.8, False), ("SPARE_2", 5, 0.5, True)):
    y = LANE[net]
    for jack, layer in ((p, B), (q, F)):
        x, ypin = jack[pin]
        if inner_row:
            L.track(net, layer, [(x, ypin), (x, SQUEEZE_Y)], 0.2)
            L.track(net, layer, [(x, SQUEEZE_Y), (x, y)], width)
        else:
            L.track(net, layer, [(x, ypin), (x, y)], width)
    L.track(net, B, [(p[pin][0], y), (q[pin][0], y)], width)
    L.via(net, q[pin][0], y, *((0.8, 0.4) if width > 0.3 else (0.6, 0.3)))
L.track("SPARE_1", B, [p[4], (p[4][0], LANE["SPARE_1"]), (q[4][0], LANE["SPARE_1"]), q[4]], 0.5)

# South of the pins: the 24 VAC pair on the bottom layer, +12 V above it on the top layer.
Y_12V, Y_ACB, Y_ACA = 41.3, 41.5, 42.9
L.track("BUS_12V", F, [p[3], (p[3][0], Y_12V), (IN_EDGE, Y_12V)], 0.8)
L.track("BUS_12V", F, [(IN_EDGE, Y_12V), (45.7, Y_12V)], 0.8)
L.track("BUS_12V", F, [(45.7, Y_12V), (q[3][0], Y_12V), q[3]], 0.8)

X_ACB_UP = 59.8  # 24 VAC b passes the OUT jack's peg and comes back to its pin from the right
L.track("AC_A", B, [p[1], (IN_EDGE, p[1][1])], 0.8)
L.track("AC_A", B, [(IN_EDGE, p[1][1]), (25.9, p[1][1]), (25.9, Y_ACA), (65.3, Y_ACA)], 0.8)
L.track("AC_B", B, [p[2], (IN_EDGE, p[2][1])], 0.8)
L.track("AC_B", B, [(IN_EDGE, p[2][1]), (27.2, p[2][1]), (27.2, Y_ACB), (X_ACB_UP, Y_ACB), (X_ACB_UP, q[2][1]), (OUT_EDGE, q[2][1])], 0.8)
L.track("AC_B", B, [(OUT_EDGE, q[2][1]), q[2]], 0.8)

# --- 24 VAC protection and spare jumpers, right of the OUT jack ---------------------------------
d4_a, d4_b = L.pad("D4", 1), L.pad("D4", 2)
f2_a, f2_com = L.pad("F2", 1), L.pad("F2", 2)
# 24 VAC a reaches the OUT jack's pin through the TVS pad.
L.via("AC_A", 65.3, Y_ACA, 0.8, 0.4)
L.track("AC_A", F, [(65.3, Y_ACA), (65.3, 41.3), d4_a], 0.8)
L.track("AC_A", F, [d4_a, (60.9, d4_a[1]), (60.9, q[1][1]), (OUT_EDGE, q[1][1])], 0.8)
L.track("AC_A", F, [(OUT_EDGE, q[1][1]), q[1]], 0.8)
L.track("AC_A", F, [(65.3, 41.3), (f2_a[0], 41.3)], 0.8)
# 24 VAC b: jumper pad, via, TVS pad in one line; the bottom-layer trunk to the outputs starts at the via.
jp2_sp, jp2_ac = L.pad("JP_SPARE_2", 1), L.pad("JP_SPARE_2", 2)
L.track("AC_B", F, [(jp2_ac[0], jp2_ac[1] + 0.2), d4_b], 0.8)  # starts on the far half of the pad: 0.5 mm to the other one
L.via("AC_B", jp2_ac[0], 34.8, 0.8, 0.4)
L.track("AC_B", B, [(X_ACB_UP, q[2][1]), (jp2_ac[0], q[2][1]), (jp2_ac[0], 34.8)], 0.8)
L.track("AC_B", B, [(jp2_ac[0], q[2][1]), (X_TRUNK, q[2][1]), (X_TRUNK, L.pad("OUT2.Q", 1)[1])], 0.8)
L.track("AC_B", B, [(X_TRUNK, q[2][1]), (X_TRUNK, L.pad("OUT1.Q", 1)[1])], 0.8)
# Valve terminal block: poles 1 and 3 are the valve outputs, 2 and 4 the fused common. Each pole
# has two pins, a rear and a front one, 7.62 mm apart. `L.pad` returns the rear one. Pole 3 joins
# its pins on the top layer, the others on the bottom layer, so that the common can cross pole 3
# below and output 2's monitor can cross poles 1 and 2 above.
PIN_ROWS = 7.62
valve_pin = {n: L.pad("J_VALVES", n) for n in (1, 2, 3, 4)}
front_pin = {n: (x, y + PIN_ROWS) for n, (x, y) in valve_pin.items()}
for n, net, layer in ((1, "VALVE1", B), (2, "AC_COM", B), (3, "VALVE2", F), (4, "AC_COM", B)):
    L.track(net, layer, [valve_pin[n], front_pin[n]], 0.8)
y_mid = valve_pin[2][1] + PIN_ROWS / 2
L.track("AC_COM", B, [(valve_pin[2][0], y_mid), (valve_pin[4][0], y_mid)], 0.8)
# Fused valve common: along the board edge, then up past output 1 to the front pin of pole 2.
X_COM, Y_COM = 85.2, 42.3
L.track("AC_COM", F, [f2_com, (f2_com[0], Y_COM), (X_COM, Y_COM), (X_COM, front_pin[2][1] + X_COM - front_pin[2][0]), front_pin[2]], 0.8)
# Spare pair: its lanes continue to the two open jumpers.
jp1_sp, jp1_ac = L.pad("JP_SPARE_1", 1), L.pad("JP_SPARE_1", 2)
L.track("SPARE_2", B, [(q[5][0], LANE["SPARE_2"]), (PASS_EDGE, LANE["SPARE_2"])], 0.5)
L.track("SPARE_2", B, [(PASS_EDGE, LANE["SPARE_2"]), (65.0, LANE["SPARE_2"])], 0.5)
L.via("SPARE_2", 65.0, LANE["SPARE_2"], 0.8, 0.4)
L.track("SPARE_2", F, [(65.0, LANE["SPARE_2"]), (65.0, jp2_sp[1]), jp2_sp], 0.5)
L.track("SPARE_1", B, [(q[4][0], LANE["SPARE_1"]), (PASS_EDGE, LANE["SPARE_1"])], 0.5)
L.track("SPARE_1", B, [(PASS_EDGE, LANE["SPARE_1"]), (jp1_sp[0], LANE["SPARE_1"]), (jp1_sp[0], 32.6)], 0.5)
L.via("SPARE_1", jp1_sp[0], 32.6, 0.8, 0.4)
L.track("SPARE_1", F, [(jp1_sp[0], 32.6), jp1_sp], 0.5)
L.track("AC_A", F, [(jp1_ac[0], jp1_ac[1] + 0.2), (jp1_ac[0], 37.3), (f2_a[0], 38.5), f2_a], 0.8)

# --- Valve outputs ------------------------------------------------------------------------------
for out in OPTO_Y:  # what both have in common: the monitor's pins
    mon_led, mon_ac = L.pad(out + ".U_MON", 1), L.pad(out + ".U_MON", 2)
    L.track(out + ".MON_LED", F, [mon_led, L.pad(out + ".R_MON", 2)], 0.8)
    L.track("AC_B", F, [mon_ac, (X_TRUNK, mon_ac[1])], 0.8)
    L.via("AC_B", X_TRUNK, mon_ac[1], 0.8, 0.4)

# Output 2, behind the block.
P = lambda part, pin: L.pad("OUT2." + part, pin)
a1, tab, g = P("Q", 1), P("Q", 2), P("Q", 3)
gk_gate, gk_ac = P("R_GK", 1), P("R_GK", 2)
# Gate: optotriac, gate-to-A1 resistor, triac in one line.
L.track("OUT2.GATE", F, [P("U_DRV", 4), gk_gate, (g[0] - 1.1 - (gk_gate[1] - g[1]), gk_gate[1]), (g[0] - 1.1, g[1]), g], 0.8)
L.track("OUT2.OPTO", F, [P("U_DRV", 6), P("R_GATE", 2)], 0.8)
# 24 VAC b: up from the trunk at the resistor, and at the trunk's end to the A1 lead.
L.track("AC_B", F, [gk_ac, (X_TRUNK, gk_ac[1])], 0.8)
L.via("AC_B", X_TRUNK, gk_ac[1], 0.8, 0.4)
X_A1_VIA = 73.3
L.track("AC_B", B, [(X_TRUNK, a1[1]), (X_A1_VIA, a1[1])], 0.8)
L.via("AC_B", X_A1_VIA, a1[1], 0.8, 0.4)
L.track("AC_B", F, [(X_A1_VIA, a1[1]), a1], 0.8)
# ... and on along the board edge on the bottom layer to the snubber capacitor.
snub_ac, x_via = P("C_SNUB", 2), 87.7
L.track("AC_B", B, [(X_A1_VIA, a1[1]), (x_via - (a1[1] - snub_ac[1]), a1[1]), (x_via, snub_ac[1])], 0.8)
L.via("AC_B", x_via, snub_ac[1], 0.8, 0.4)
L.track("AC_B", F, [snub_ac, (x_via, snub_ac[1])], 0.8)
L.track("OUT2.SNUB", F, [P("R_SNUB", 2), P("C_SNUB", 1)], 0.8)
# The valve node: gate resistor between the triac's leads to the tab; tab, snubber resistor, pole 3;
# monitor resistor under the block, between its pin rows, to pole 3.
r_gate, r_snub, r_mon = P("R_GATE", 1), P("R_SNUB", 1), P("R_MON", 1)
L.track("VALVE2", F, [r_gate, (tab[0] - 2.2, r_gate[1])], 0.8)
L.track("VALVE2", F, [(tab[0] + 1.7, r_snub[1]), (valve_pin[3][0], r_snub[1]), valve_pin[3]], 1.2)
L.track("VALVE2", F, [r_mon, (valve_pin[3][0], r_mon[1])], 0.8)
# A copper area that also cools the triac (ST DocID7699 Rev 9: 70 K/W assumes 0.5 cm2 of copper under the tab).
L.zone("VALVE2", F, outline=[(77.9, 0.6), (85.2, 0.6), (85.2, 5.9), (88.2, 5.9), (88.2, 10.9), (85.0, 10.9), (85.0, 7.4), (77.9, 7.4)], solid=True)

# Output 1, in front of the block.
P = lambda part, pin: L.pad("OUT1." + part, pin)
a1, tab, g = P("Q", 1), P("Q", 2), P("Q", 3)
gk_gate, gk_ac = P("R_GK", 1), P("R_GK", 2)
drv_gate, drv_opto = P("U_DRV", 4), P("U_DRV", 6)
# Gate: past the tab, then between tab and leads to the gate lead and on to the gate-to-A1 resistor.
Y_GAP = g[1] - 2.1  # 0.6 mm to the tab above and to the leads below
L.track("OUT1.GATE", F, [drv_gate, (71.2, drv_gate[1]), (72.2, drv_gate[1] + 1.0), (72.2, Y_GAP - 1.0), (73.2, Y_GAP), (g[0], Y_GAP), g], 0.8)
L.track("OUT1.GATE", F, [g, gk_gate], 0.8)
r_opto = P("R_GATE", 2)
L.track("OUT1.OPTO", F, [drv_opto, (r_opto[0] - (r_opto[1] - drv_opto[1]), drv_opto[1]), r_opto], 0.8)
# 24 VAC b: up from the trunk's end to the A1 lead; a branch under the triac to the column beside it.
snub_ac = P("C_SNUB", 2)
L.via("AC_B", X_TRUNK, a1[1], 0.8, 0.4)
L.track("AC_B", F, [(X_TRUNK, a1[1]), a1], 0.8)
y_branch, x_via = (snub_ac[1] + gk_ac[1]) / 2, snub_ac[0] + 1.5
L.track("AC_B", B, [(X_TRUNK, y_branch), (x_via, y_branch)], 0.8)
L.via("AC_B", x_via, y_branch, 0.8, 0.4)
L.track("AC_B", F, [(x_via, y_branch), (snub_ac[0], y_branch)], 0.8)
L.track("AC_B", F, [snub_ac, gk_ac], 0.8)
L.track("OUT1.SNUB", F, [P("R_SNUB", 2), P("C_SNUB", 1)], 0.8)
# The valve node: pole 1 straight into the tab; gate and monitor resistors; tab to the snubber resistor.
r_gate, r_snub, r_mon = P("R_GATE", 1), P("R_SNUB", 1), P("R_MON", 1)
L.track("VALVE1", F, [front_pin[1], (front_pin[1][0], tab[1] - 2.2)], 1.5)
L.track("VALVE1", F, [r_gate, (r_gate[0] + 0.84, r_gate[1] + 0.84), (front_pin[1][0], r_gate[1] + 0.84)], 0.8)
L.track("VALVE1", F, [r_mon, (front_pin[1][0] - (r_mon[1] - front_pin[1][1]), r_mon[1]), front_pin[1]], 0.8)
L.track("VALVE1", F, [(tab[0] + 2.2, r_snub[1]), r_snub], 0.8)
L.zone("VALVE1", F, outline=[(74.0, 16.0), (79.3, 16.0), (79.3, 19.2), (80.4, 19.2), (80.4, 37.0), (74.0, 37.0)], solid=True)

# --- Bus protection between the jacks -----------------------------------------------------------
# RS485: each lane rises through a via straight into its TVS pad; the TVS's ground pad goes back to
# the ground lane with a short wide track (TI SLLSF20B, 11.1, p. 21).
d3_a, d3_b, d3_gnd = L.pad("D3", 1), L.pad("D3", 2), L.pad("D3", 3)
L.via("BUS_A", d3_a[0], LANE["BUS_A"])
L.track("BUS_A", F, [(d3_a[0], LANE["BUS_A"]), d3_a], 0.3)
L.via("BUS_B", d3_b[0], LANE["BUS_B"])
L.track("BUS_B", F, [(d3_b[0], LANE["BUS_B"]), d3_b], 0.3)
L.track("GND", F, [d3_gnd, (34.6, d3_gnd[1]), (34.6, LANE["GND"])], 0.8)
L.via("GND", 34.6, LANE["GND"], 0.8, 0.4)
# +12 V: lane, fuse, TVS to the ground lane, series diode, input capacitor.
f1_bus, f1_out = L.pad("F1", 1), L.pad("F1", 2)
d1_gnd, d1_12 = L.pad("D1", 1), L.pad("D1", 2)
d2_k, d2_a = L.pad("D2", 1), L.pad("D2", 2)
L.track("BUS_12V", F, [(f1_bus[0], Y_12V), f1_bus], 0.8)
L.track("V12_F", F, [f1_out, (f1_out[0], 32.6), d1_12], 0.8)
L.track("V12_F", F, [f1_out, (d2_a[0], f1_out[1]), d2_a], 0.8)
L.track("GND", F, [d1_gnd, (d1_gnd[0], LANE["GND"])], 0.8)
L.via("GND", d1_gnd[0], LANE["GND"], 0.8, 0.4)
L.track("VIN", F, [d2_k, L.pad("C_VIN", 1)], 0.8)

# --- Microcontroller ----------------------------------------------------------------------------
# Ground goes inwards to the exposed pad, which a via ties to the bottom-layer ground; +5 V goes
# straight to its capacitor.
mcu = {n: L.pad("U_MCU", n) for n in (3, 4, 21)}
fan = L.fanout("U_MCU", skip=("3", "4"))
L.track("GND", F, [mcu[3], mcu[21]], 0.2)
L.via("GND", *mcu[21])
L.track("+5V", F, [mcu[4], (52.3, mcu[4][1]), (52.7, mcu[4][1] - 0.4)], 0.2)

# --- Ground: the logic half only ----------------------------------------------------------------
X_GND = X_LOGIC + 1.16  # up to the optocouplers' logic pads
L.zone("GND", F, outline=[(0.5, 0.5), (X_GND, 0.5), (X_GND, 26.4), (42.6, 26.4), (42.6, 39.6), (28.5, 39.6), (28.5, 26.4), (0.5, 26.4)])
L.zone("GND", B, outline=rect(0.5, 0.5, X_GND, 26.4))

L.solid("J_UPDI", 3)
for out in OPTO_Y:  # ground pins between two neighbours and the isolation gap: no room for spokes
    L.solid(out + ".U_DRV", 2)
    L.solid(out + ".U_MON", 3)

# --- The rest of the logic side: grid router -----------------------------------------------------
# Its region ends 3 mm before any 24 VAC copper and before the lanes of the pass-through.
# Signal tracks are 0.2 mm wide with 0.2 mm space: the microcontroller's pins are 0.4 mm apart.
# (The Default class in the KiCad project says 0.3 mm; that is a nominal width for drawing by
# hand, from lib/jlcpcb.zen, not a limit. The limit is 0.15 mm.)
R = L.router((8.0, 0.6, X_GND - 0.1, 26.3))
for net, (x, y) in fan:
    R.reserve(net, x, y)
R.stitch("GND", ["C_MCU.2"])  # first, while there is room next to the microcontroller
R.route("+5V", width=0.4, only=["C_MCU.1", "J_UPDI.2"])  # likewise: output 2's signals pass around this capacitor
for net in ("TXD", "RXD", "XDIR", "ADDR1", "ADDR2", "ADDR3", "ADDR4", "UPDI",
            "DRIVE2", "MON2", "OUT2.LED_A", "DRIVE1", "MON1", "OUT1.LED_A", "LED", "LED_A",
            "BUS_A", "BUS_B", "PB1", "PB4", "PB5", "PA3", "PA1"):
    R.route(net)
for net in ("VIN", "+5V"):
    R.route(net, width=0.4)
# Every ground pad gets its own via to the bottom-layer zone: the top-layer zone is cut into
# islands by the tracks above.
R.stitch("GND", ["C_VIN.2", "C_5V.2", "C_RS485.2", "R_XDIR.2", "U_REG.1", "U_RS485.5",
                 "SW_ADDR.5", "SW_ADDR.8", "D_STATUS.1", "TP_GND.1",
                 "OUT1.U_DRV.2", "OUT1.U_MON.3", "OUT2.U_DRV.2", "OUT2.U_MON.3"])
L.save()
print("layout: %d track segments, %d vias" % (sum(1 for t in L.manual if t.GetClass() != "PCB_VIA"), sum(1 for t in L.manual if t.GetClass() == "PCB_VIA")))
