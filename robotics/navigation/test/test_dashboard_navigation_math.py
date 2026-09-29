"""Run with python3 -m unittest discover -s robotics/navigation/test -p 'test_dashboard_navigation_math.py'."""
import math
import pathlib
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
from dashboard_navigation_math import cell_cost, map_to_world, world_to_map


def grid(yaw=0):
    return NS(info=NS(resolution=1.0, width=2, height=2,
                     origin=NS(position=NS(x=0.0, y=0.0),
                               orientation=NS(x=0, y=0, z=math.sin(yaw / 2),
                                              w=math.cos(yaw / 2)))),
              data=[0, 100, -1, 65])


class NavigationCoordinatesTest(unittest.TestCase):
    def test_transform_round_trip(self):
        for offset in [(0, 0, 0), (-1.2639, -3.9049, 0), (3, -8, math.pi / 2)]:
            pose = (-4.5, 0.25, -1.0)
            result = world_to_map(*map_to_world(*pose, offset), offset)
            for actual, expected in zip(result, pose):
                self.assertAlmostEqual(actual, expected)

    def test_rotated_map_to_world(self):
        x, y, yaw = map_to_world(1, 0, 0, (3, -2, math.pi / 2))
        self.assertAlmostEqual(x, 3)
        self.assertAlmostEqual(y, -1)
        self.assertAlmostEqual(yaw, math.pi / 2)

    def test_occupied_unknown_and_outside_cells(self):
        g = grid()
        self.assertEqual(cell_cost(g, 0.5, 0.5), 0)
        self.assertEqual(cell_cost(g, 1.5, 0.5), 100)
        self.assertEqual(cell_cost(g, 0.5, 1.5), -1)
        self.assertEqual(cell_cost(g, 1.5, 1.5), 65)
        self.assertEqual(cell_cost(g, -0.001, 0.5), -1)
        self.assertEqual(cell_cost(g, 2.0, 0.5), -1)

    def test_rotated_grid_origin(self):
        self.assertEqual(cell_cost(grid(math.pi / 2), -0.5, 1.5), 100)

    def test_invalid_grid(self):
        g = grid()
        g.data = []
        self.assertEqual(cell_cost(g, 0.5, 0.5), -1)
        g.info.resolution = 0
        self.assertEqual(cell_cost(g, 0.5, 0.5), -1)


if __name__ == '__main__':
    unittest.main()
