"""Placement and routing of the throwaway board. Run via `make layout BOARD=throwaway`."""
import os

import pcbnew
from kilayout import Layout

L = Layout(os.path.dirname(os.path.abspath(__file__)), "throwaway")
L.clear()
L.outline_from_mech()
L.place_mounting_holes()

# Signal flow left to right: connector, input cap, regulator, output cap, LED.
L.place("J1", 6.0, 11.5, rot=0)
L.place("C1", 12.0, 12.5, rot=90)
L.place("U1", 19.5, 12.5, rot=0)
L.place("C2", 27.0, 12.5, rot=90)
L.place("R1", 31.5, 9.0, rot=90)
L.place("D1", 35.0, 9.0, rot=90)
L.check_all_placed()

L.zone("GND", pcbnew.B_Cu)
L.autoroute()
