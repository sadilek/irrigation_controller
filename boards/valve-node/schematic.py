"""Arrangement of the valve node schematic. Run via `make arrange BOARD=valve-node`.

Positions only: which pin is on which net is decided in valve-node.zen and output.zen.
Each block is drawn relative to its top-left corner, in millimetres on the 1.27 mm grid.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from schlayout import Schematic  # noqa: E402

S = Schematic(os.path.dirname(os.path.abspath(__file__)), "valve-node", paper="A3")
S.power = {"GND": ("GND", "down"), "+5V": ("VCC", "up"), "VIN": ("VCC", "up")}
S.title(
    "Valve node",
    "A",
    [
        "Modbus RTU over RS485, two 24 VAC valve outputs",
        "Crossed-out parts are footprints without parts (population options)",
        "Part numbers: bill of materials. Reasoning: docs/valve-node-spec.md",
    ],
)

G = 2.54


def bus_jacks(x, y):
    S.box(x, y, x + 119.38, y + 81.28, "Bus: two RJ45 jacks, all eight wires passed through")
    S.place("J_IN", x + 20.32, y + 30.48)
    S.place("J_OUT", x + 99.06, y + 30.48, mirror="y")
    colours = ["orange/white", "orange", "green/white", "blue", "blue/white", "green", "brown/white", "brown"]
    for pin in range(1, 9):
        a = S.at("J_IN.%d" % pin)
        b = S.at("J_OUT.%d" % pin)
        S.wire("J_IN.%d" % pin, "J_OUT.%d" % pin)
        S.text(b[0] - 26.67, a[1] - 2.1, "%d  %s" % (pin, colours[pin - 1]), size=1.1)
        if pin != 6:
            S.label((a[0] + G, a[1]), (1, 0), net=S.net_of[(S.part("J_IN").ref, str(pin))])
    # Ground leaves the pass-through downwards, across the wires of pins 5 to 1 (no connection there).
    gx = S.at("J_IN.6")[0] + 10 * G
    S.wire((gx, S.at("J_IN.6")[1]), (gx, y + 48.26))
    S.power_symbol((gx, y + 48.26), net="GND")
    S.text(x + G, y + 8.0, "IN", size=2.0, bold=True)
    S.text(x + 109.22, y + 8.0, "OUT", size=2.0, bold=True)

    # Spare pair in parallel to the 24 VAC pair: both jumpers open by default.
    S.text(x + G, y + 55.0, "Spare pair doubles the 24 VAC pair when both jumpers are closed (default: open)", size=1.27)
    S.place("JP_SPARE_1", x + 30.48, y + 66.04, value=False)
    S.place("JP_SPARE_2", x + 81.28, y + 66.04, value=False)
    S.text(x + G, y + 73.5, "A bus cable must never be plugged into network equipment: pins 1 and 2 carry 24 VAC.", size=1.27)


def supply(x, y):
    S.box(x, y, x + 132.08, y + 45.72, "12 V input and 5 V regulator")
    yl = y + 20.32
    S.place("F1", x + 20.32, yl, rot=90)
    S.place("D1", x + 33.02, yl + 3 * G, rot=90)
    S.place("D2", x + 45.72, yl, mirror="y")
    S.place("C_VIN", x + 58.42, yl + 3 * G, value=(1.9, 1.2))
    S.place("TP_VIN", x + 66.04, yl - 2 * G, ref=(1.5, -1.0), value=False)
    S.place("U_REG", x + 83.82, yl + G, ref=(-5.0, -9.6), value=(-5.0, -7.8))
    S.place("C_5V", x + 101.6, yl + 3 * G, ref=(1.9, -1.1), value=(1.9, 1.2))
    S.place("TP_5V", x + 109.22, yl - 2 * G, ref=(1.5, -1.0), value=False)
    S.place("TP_GND", x + 121.92, yl + 3 * G, ref=(1.5, -1.0), value=False)
    rail = yl + 7 * G
    S.wire("F1.2", "D2.2")
    S.wire("D1.2", (x + 33.02, yl))
    S.wire("D2.1", "U_REG.2")
    S.wire("C_VIN.1", (x + 58.42, yl))
    S.wire("TP_VIN.1", (x + 66.04, yl))
    S.wire("U_REG.3", (x + 121.92, yl), (x + 121.92, yl - G))
    S.power_symbol((x + 121.92, yl - G), net="+5V")
    S.wire("C_5V.1", (x + 101.6, yl))
    S.wire("TP_5V.1", (x + 109.22, yl))
    S.wire("D1.1", (x + 33.02, rail), (x + 121.92, rail), "TP_GND.1")
    S.wire("C_VIN.2", (x + 58.42, rail))
    S.wire("U_REG.1", (x + 83.82, rail))
    S.wire("C_5V.2", (x + 101.6, rail))
    S.wire((x + 71.12, rail), (x + 71.12, rail + G))
    S.power_symbol((x + 71.12, rail + G), net="GND")
    S.label((x + 38.1, yl), (0, -1), net="V12_F")
    S.label((x + 53.34, yl), (0, -1), net="VIN")


def rs485(x, y):
    S.box(x, y, x + 132.08, y + 71.12, "RS485")
    ux, uy = x + 71.12, y + 35.56
    S.place("U_RS485", ux, uy, ref=(2.5, -17.2), value=(2.5, -15.4))
    lx, rx = ux - 10.16, ux + 10.16
    ya, yb = uy - 7.62, uy - 2.54
    # Driver enable and receiver enable on one net: the node does not hear its own answer.
    S.wire("U_RS485.2", (lx - 5 * G, uy - G))
    S.wire("U_RS485.3", (lx - G, uy), (lx - G, uy - G))
    S.label((lx - 5 * G, uy - G), (-1, 0), net="XDIR")
    S.place("R_XDIR", x + 15.24, y + 58.42)
    S.place("C_RS485", x + 33.02, y + 58.42, value=(1.9, 1.2))

    # A/B swap jumpers and bias footprints on the transceiver side.
    S.place("JP_A", rx + 9 * G, ya - 4 * G, rot=270, pin="2", ref=(2.5, -0.6), value=False)
    S.place("JP_B", rx + 12 * G, yb + 6 * G, rot=270, pin="2", ref=(2.5, -0.6), value=False)
    S.wire("U_RS485.6", (rx + 3 * G, ya), (rx + 3 * G, ya - 4 * G), "JP_A.2")
    S.wire("U_RS485.7", (rx + 3 * G, yb), (rx + 3 * G, yb + 6 * G), "JP_B.2")
    S.place("R_BIAS_A", rx + 6 * G, ya - 6 * G)
    S.wire("R_BIAS_A.2", (rx + 6 * G, ya - 4 * G))
    S.place("R_BIAS_B", rx + 6 * G, yb + 8 * G)
    S.wire("R_BIAS_B.1", (rx + 6 * G, yb + 6 * G))
    S.label((rx + G, ya), (1, 0), net="RS_A")
    S.label((rx + G, yb), (1, 0), net="RS_B")
    S.text(x + 45.0, y + 62.0, "Swap A and B: cut the bridges 1-2\nof JP1 and JP2, solder 2-3", size=1.27)

    # At the jacks: TVS, and the termination that stays open.
    S.place("D3", x + 20.32, y + 15.24)
    S.place("R_TERM", x + 15.24, y + 38.1, rot=90)
    S.place("JP_TERM", x + 22.86, y + 38.1, pin="1", value=False)
    S.wire("R_TERM.2", "JP_TERM.1")
    S.text(x + G, y + 41.5, "Termination: open on every node", size=1.27)


def mcu(x, y):
    S.box(x, y, x + 132.08, y + 81.28, "Microcontroller")
    mx, my = x + 76.2, y + 40.64
    S.place("U_MCU", mx, my, ref=(-12.7, -24.6), value=(-12.7, -22.8))
    S.place("C_MCU", x + 38.1, y + 22.86, value=(1.9, 1.2))
    # Address switch: a closed switch pulls the pin low.
    S.place("SW_ADDR", mx - 15.24 - 4 * G, my + 5.08, mirror="y", pin="1", ref=(-3.8, -10.5), value=(-3.8, 9.0))
    gx = mx - 15.24 - 11 * G
    for n in range(1, 5):
        S.wire("SW_ADDR.%d" % n, "U_MCU.%d" % (14 + n))
        S.wire("SW_ADDR.%d" % (9 - n), (gx, S.at("SW_ADDR.%d" % (9 - n))[1]))
    S.wire((gx, S.at("SW_ADDR.8")[1]), (gx, my + 6 * G))
    S.power_symbol((gx, my + 6 * G), net="GND")
    S.text(x + G, y + 70.0, "Address 1 to 15, binary,\nswitch 1 = lowest bit, ON = 1", size=1.27)

    # Status LED
    S.place("R_LED", x + 106.68, y + 68.58, rot=90)
    S.place("D_STATUS", x + 116.84, y + 68.58, mirror="y", value=False)
    S.wire("R_LED.2", "D_STATUS.2")
    S.wire("D_STATUS.1", (x + 124.46, y + 68.58), (x + 124.46, y + 71.12))
    S.power_symbol((x + 124.46, y + 71.12), net="GND")

    # Programming header: UPDI, 5 V, ground.
    S.place("J_UPDI", x + 124.46, y + 20.32, ref=(-1.3, -6.6), value=False)
    S.text(x + 112.0, y + 34.5, "UPDI header", size=1.27)
    px = S.at("J_UPDI.2")[0]
    S.wire("J_UPDI.2", (px - 5 * G, y + 20.32), (px - 5 * G, y + 20.32 - 3 * G))
    S.power_symbol((px - 5 * G, y + 20.32 - 3 * G), net="+5V")
    S.wire("J_UPDI.3", (px - G, y + 22.86), (px - G, y + 22.86 + 2 * G))
    S.power_symbol((px - G, y + 22.86 + 2 * G), net="GND")
    # Pads on the five unused pins.
    for i, name in enumerate(("TP_PA1", "TP_PA3", "TP_PB1", "TP_PB4", "TP_PB5")):
        S.place(name, x + 17.78, y + 15.24 + i * 2 * G, rot=270, ref=(1.6, -0.6), value=False)


def ac_protection(x, y):
    S.box(x, y, x + 119.38, y + 43.18, "24 VAC: clamp and valve fuse", "Isolated from the logic: no connection to GND.")
    S.place("D4", x + 25.4, y + 26.67, rot=90)
    S.place("F2", x + 71.12, y + 26.67, rot=90)


def output(n, x, y):
    S.box(x, y, x + 132.08, y + 55.88, "Valve output %d" % n)
    o = "OUT%d." % n
    top, bottom = y + 17.78, y + 48.26  # valve rail, 24 VAC b rail
    yd = y + 25.4  # drive line
    S.place(o + "R_LED", x + 16.51, yd, rot=90)
    S.place(o + "U_DRV", x + 31.75, yd + G, ref=(-8.9, -6.7), value=(-8.9, -4.9))
    S.wire(o + "R_LED.2", o + "U_DRV.1")
    S.wire(o + "U_DRV.2", (x + 21.59, yd + 2 * G), (x + 21.59, yd + 3 * G))
    S.power_symbol((x + 21.59, yd + 3 * G), net="GND")
    S.place(o + "R_GATE", x + 46.99, yd, rot=270)
    S.wire(o + "U_DRV.6", o + "R_GATE.2")
    S.wire(o + "R_GATE.1", (x + 54.61, yd), (x + 54.61, top))
    S.place(o + "Q", x + 67.31, yd + 6.35 + G, ref=(3.2, -1.0), value=(3.2, 0.9))
    gate = S.at(o + "Q.3")
    S.wire(o + "U_DRV.4", (x + 57.15, yd + 2 * G), (x + 57.15, gate[1]), o + "Q.3")
    S.place(o + "R_GK", x + 57.15, gate[1] + 2 * G)
    S.wire(o + "R_GK.1", (x + 57.15, gate[1]))
    S.wire(o + "R_GK.2", (x + 57.15, bottom))
    S.wire(o + "Q.2", (x + 67.31, top))
    S.wire(o + "Q.1", (x + 67.31, bottom))
    S.place(o + "R_SNUB", x + 87.63, top + 2 * G)
    S.place(o + "C_SNUB", x + 87.63, top + 8 * G, value=(1.9, 1.2))
    S.wire((x + 87.63, top), o + "R_SNUB.1")
    S.wire(o + "R_SNUB.2", o + "C_SNUB.1")
    S.wire(o + "C_SNUB.2", (x + 87.63, bottom))
    S.place(o + "R_MON", x + 97.79, top + 2 * G)
    S.place(o + "U_MON", x + 111.76, top + 6 * G, ref=(-8.9, -6.7), value=(-8.9, -4.9))
    S.wire((x + 97.79, top), o + "R_MON.1")
    S.wire(o + "R_MON.2", (x + 97.79, S.at(o + "U_MON.1")[1]), o + "U_MON.1")
    S.wire(o + "U_MON.2", (x + 101.6, S.at(o + "U_MON.2")[1]), (x + 101.6, bottom))
    S.wire(o + "U_MON.3", (x + 124.46, S.at(o + "U_MON.3")[1]), (x + 124.46, S.at(o + "U_MON.3")[1] + G))
    S.power_symbol((x + 124.46, S.at(o + "U_MON.3")[1] + G), net="GND")
    S.place(o + "J", x + 119.38, top - 2 * G, pin="1", ref=(1.3, -4.6, "right"), value=(1.3, -2.8, "right"))
    S.wire((x + 54.61, top), (x + 111.76, top), (x + 111.76, top - 2 * G), o + "J.1")
    S.wire((x + 52.07, bottom), (x + 101.6, bottom))
    S.label((x + 52.07, bottom), (-1, 0), net="AC_B")
    S.text(x + 2.0, y + 50.8, "logic side", size=1.27)
    S.text(x + 106.0, y + 50.8, "logic side", size=1.27)
    S.text(x + 60.0, y + 50.8, "24 VAC side", size=1.27)


def notes(x, y):
    S.box(x, y, x + 119.38, y + 43.18, "Mounting and notes")
    for i in range(4):
        S.place("H%d" % (i + 1), x + 10.16 + i * 12.7, y + 15.24, ref=(-1.5, 2.2), value=False)
    S.text(x + 60.0, y + 13.5, "4 x M3", size=1.27)
    S.text(
        x + G,
        y + 22.0,
        "Population options (crossed-out parts are not populated):\n"
        "- termination, bias resistors, UPDI header",
        size=1.27,
    )


bus_jacks(12.7, 12.7)
supply(137.16, 12.7)
rs485(137.16, 60.96)
mcu(271.78, 12.7)
ac_protection(12.7, 96.52)
notes(12.7, 142.24)
for n in range(2):
    output(n + 1, 137.16 + n * 134.62, 134.62)
S.finish()
