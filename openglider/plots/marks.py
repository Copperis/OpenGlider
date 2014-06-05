import math
from openglider.vector import rotation_2d, Vectorlist2D

sign_size = 0.8


def polygon(p1, p2, rotation=False, num=3, size=sign_size, is_center=False):
    """Polygon"""
    if not is_center:
        center = (p1+p2)/2
    else:
        center = p1
    diff = (p2-center) * size

    return [Vectorlist2D([center + rotation_2d(math.pi*2*i/num+rotation).dot(diff) for i in range(num+1)])]


def triangle(p1, p2, size=sign_size):
    return polygon(p1, p2, num=3, size=size)


def line(p1, p2, rotation=False):
    if not rotation:
        return [Vectorlist2D([p1, p2])]
    else:
        center = (p1+p2)/2
        rot = rotation_2d(rotation)
        return [Vectorlist2D([center + rot.dot(p1-center), center+rot.dot(p2-center)])]


def cross(p1, p2, rotation=False):
    return line(p1, p2, rotation=rotation) + line(p1, p2, rotation=rotation+math.pi/2)



