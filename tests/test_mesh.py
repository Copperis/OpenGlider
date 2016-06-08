import unittest


from common import *

from openglider.mesh import Mesh, Vertex
from openglider.physics.base import GliderCase
import openglider


class TestMesh(TestCase):
    def setUp(self, complete=True):
        self.glider = openglider.load("./common/demokite.json").get_glider_3d()

    def test_mesh(self):
        p1 = Vertex(*[0, 0, 0])
        p2 = Vertex(*[1, 0, 0])
        p3 = Vertex(*[0, 1, 0])
        p4 = Vertex(*[1, 1, 0])
        p5 = Vertex(*[0, 0, 0])
        a = [p1, p2, p3, p4]
        b = [p1, p2, p4, p5]
        m1 = Mesh({"a": [a]}, boundary_nodes={"j": a})
        m2 = Mesh({"b": [b]}, boundary_nodes={"j": b})
        m3 = m1 + m2
        m3.delete_duplicates()
        for vertex in a:
            self.assertTrue(vertex in m3.vertices)

    def test_GliderCase(self):
        test = self.glider.copy_complete()
        GliderCase(test)


if __name__ == '__main__':
    unittest.main(verbosity=2)
