from __future__ import division

from openglider.glider.parametric.arc import ArcCurve
from openglider.glider.parametric.shape import ParametricShape

try:
    import ezodf2 as ezodf
except ImportError:
    import ezodf

import numpy
from openglider.airfoil import BezierProfile2D, Profile2D
from openglider.glider.ballooning import BallooningBezier
from openglider.vector.spline import Bezier, SymmetricBezier
from openglider.vector import Interpolation
from .lines import UpperNode2D, LowerNode2D, BatchNode2D, Line2D, LineSet2D

element_keywords = {
    "cuts": ["cells", "left", "right", "type"],
    "a": "",
}


def import_ods_2d(Glider2D, filename, numpoints=4):
    ods = ezodf.opendoc(filename)
    sheets = ods.sheets

    main_sheet = sheets[0]
    cell_sheet = sheets[1]
    rib_sheet = sheets[2]

    # file-version
    if cell_sheet[0, 0].value == "V2" or cell_sheet[0, 0].value == "V2":
        file_version = 2
    else:
        file_version = 1
    # ------------

    # profiles = [BezierProfile2D(profile) for profile in transpose_columns(sheets[3])]
    profiles = [Profile2D(profile) for profile in transpose_columns(sheets[3])]

    balloonings_temp = transpose_columns(sheets[4])
    balloonings = []
    for baloon in balloonings_temp:
        if baloon:
            upper = [[0, 0]] + baloon[:8] + [[1, 0]]
            lower = [[0, 0]] + [[i[0], -1 * i[1]] for i in baloon[8:16]] + [[1, 0]]
            balloonings.append(BallooningBezier(upper, lower))

    data = {}
    datasheet = sheets[-1]
    assert isinstance(datasheet, ezodf.Sheet)
    for row in datasheet.rows():
        if len(row) > 1:
            data[row[0].value] = row[1].value

    # All Lists
    front = []
    back = []
    cell_distribution = []
    aoa = []
    arc = []
    profile_merge = []
    ballooning_merge = []
    zrot = []

    y = z = span_last = alpha = 0.

    assert isinstance(main_sheet, ezodf.Sheet)
    for i in range(1, main_sheet.nrows() + 1):
        line = [main_sheet.get_cell([i, j]).value for j in range(main_sheet.ncols())]
        if not line[0]:
            break  # skip empty line
        # Index, Choord, Span(x_2d), Front(y_2d=x_3d), d_alpha(next), aoa,
        chord = line[1]
        span = line[2]
        x = line[3]
        y += numpy.cos(alpha) * (span - span_last)
        z -= numpy.sin(alpha) * (span - span_last)

        alpha += line[4] * numpy.pi / 180  # angle after the rib

        aoa.append([span, line[5] * numpy.pi / 180])
        arc.append([y, z])
        front.append([span, -x])
        back.append([span, -x - chord])
        cell_distribution.append([span, i - 1])

        profile_merge.append([span, line[8]])
        ballooning_merge.append([span, line[9]])

        zrot.append([span, line[7] * numpy.pi / 180])

        span_last = span

    # Attachment points: rib_no, id, pos, force
    attachment_points = get_attachment_points(rib_sheet)
    attachment_points_lower = get_lower_aufhaengepunkte(data)

    # RIB HOLES
    rib_hole_keywords = ["ribs", "pos", "size"]
    rib_holes = read_elements(rib_sheet, "QUERLOCH", len_data=2)
    rib_holes = to_dct(rib_holes, rib_hole_keywords)
    rib_holes = group(rib_holes, "ribs")

    rigidfoil_keywords = ["ribs", "start", "end", "distance"]
    rigidfoils = read_elements(rib_sheet, "RIGIDFOIL", len_data=3)
    rigidfoils = to_dct(rigidfoils, rigidfoil_keywords)
    rigidfoils = group(rigidfoils, "ribs")

    # CUTS
    def get_cuts(names, target_name):
        objs = []
        for name in names:
            objs += read_elements(sheets[1], name, len_data=2)

        cuts = [{"cells": res[0], "left": res[1], "right": res[2], "type": target_name}
                for res in objs]

        return group(cuts, "cells")

    cuts = get_cuts(["EKV", "EKH", "orthogonal"], "folded")
    cuts += get_cuts(["DESIGNM", "DESIGNO", "orthogonal"], "orthogonal")

    # Diagonals: center_left, center_right, width_l, width_r, height_l, height_r
    # height (0,1) -> (-1,1)
    diagonals = []
    for res in read_elements(sheets[1], "QR", len_data=6):
        height1 = res[5]
        height2 = res[6]

        # migration
        if file_version == 1:
            height1 = height1 * 2 - 1
            height2 = height2 * 2 - 1
        # ---------

        diagonals.append({"left_front": (res[1] - res[3] / 2, height1),
                          "left_back": (res[1] + res[3] / 2, height1),
                          "right_front": (res[2] - res[4] / 2, height2),
                          "right_back": (res[2] + res[4] / 2, height2),
                          "cells": res[0]})
        # todo: group
    diagonals = group(diagonals, "cells")

    straps = []
    straps_keywords = ["cells", "left", "right"]
    # straps = read_elements(cell_sheet, "VEKTLAENGE", len_data=2)
    for res in read_elements(sheets[1], "VEKTLAENGE", len_data=2):
        straps.append({"cells": res[0],
                       "left": res[1],
                       "right": res[2]})
    straps = group(straps, "cells")

    has_center_cell = not front[0][0] == 0
    cell_no = (len(front) - 1) * 2 + has_center_cell

    def symmetric_fit(data):
        not_from_center = data[0][0] == 0
        mirrored = [[-p[0], p[1]] for p in data[not_from_center:]][::-1] + data
        return SymmetricBezier.fit(mirrored, numpoints=numpoints)

    start = (2 - has_center_cell) / cell_no

    const_arr = [0.] + numpy.linspace(start, 1, len(front) - (not has_center_cell)).tolist()
    rib_pos = [0.] + [p[0] for p in front[not has_center_cell:]]
    rib_pos_int = Interpolation(zip(rib_pos, const_arr))
    rib_distribution = [[i, rib_pos_int(i)] for i in numpy.linspace(0, rib_pos[-1], 30)]

    rib_distribution = Bezier.fit(rib_distribution, numpoints=numpoints + 3)

    parametric_shape = ParametricShape(symmetric_fit(front), symmetric_fit(back), rib_distribution, cell_no)
    arc_curve = ArcCurve(symmetric_fit(arc))

    glider_2d = Glider2D(shape=parametric_shape,
                         arc=arc_curve,
                         aoa=symmetric_fit(aoa),
                         zrot=symmetric_fit(zrot),
                         elements={"cuts": cuts,
                                   "holes": rib_holes,
                                   "diagonals": diagonals,
                                   "rigidfoils": rigidfoils,
                                   "straps": straps,
                                   "materials": get_material_codes(cell_sheet)},
                         profiles=profiles,
                         profile_merge_curve=symmetric_fit(profile_merge),
                         balloonings=balloonings,
                         ballooning_merge_curve=symmetric_fit(ballooning_merge),
                         lineset=tolist_lines(sheets[6], attachment_points_lower, attachment_points),
                         speed=data.get("GESCHWINDIGKEIT", 10),
                         glide=data.get("GLEITZAHL", 10))

    glider_3d = glider_2d.get_glider_3d()
    glider_2d.lineset.set_default_nodes2d_pos(glider_3d)
    return glider_2d


def get_material_codes(sheet):
    materials = read_elements(sheet, "MATERIAL", len_data=1)
    i = 0
    ret = []
    while materials:
        codes = [el[1] for el in materials if el[0] == i]
        materials = [el for el in materials if el[0] != i]
        ret.append(codes)
        i += 1
    # cell_no, part_no, code
    return ret


def get_attachment_points(sheet, midrib=False):
    # UpperNode2D(rib_no, rib_pos, force, name, layer)
    attachment_points = [UpperNode2D(args[0], args[2], args[3], args[1])
                         for args in read_elements(sheet, "AHP", len_data=3)]
    # attachment_points.sort(key=lambda element: element.nr)

    return {node.name: node for node in attachment_points}
    # return attachment_points


def get_lower_aufhaengepunkte(data):
    aufhaengepunkte = {}
    xyz = {"X": 1, "Y": 0, "Z": 2}
    for key in data:
        if key is not None and "AHP" in key:
            pos = int(key[4])
            aufhaengepunkte.setdefault(pos, [0, 0, 0])
            which = key[3].upper()
            aufhaengepunkte[pos][xyz[which]] = data[key]
    return {nr: LowerNode2D([0, 0], pos, nr)
            for nr, pos in aufhaengepunkte.items()}


def transpose_columns(sheet=ezodf.Table(), columnswidth=2):
    num = sheet.ncols()
    # if num % columnswidth > 0:
    #    raise ValueError("irregular columnswidth")
    result = []
    for col in range(int(num / columnswidth)):
        columns = range(col * columnswidth, (col + 1) * columnswidth)
        element = []
        i = 0
        while i < sheet.nrows():
            row = [sheet.get_cell([i, j]).value for j in columns]
            if sum([j is None for j in row]) == len(row):  # Break at empty line
                break
            i += 1
            element.append(row)
        result.append(element)
    return result


def tolist_lines(sheet, attachment_points_lower, attachment_points_upper):
    # upper -> dct {name: node}
    num_rows = sheet.nrows()
    num_cols = sheet.ncols()
    linelist = []
    current_nodes = [None for i in range(num_cols)]
    i = j = level = 0
    count = 0

    while i < num_rows:
        val = sheet.get_cell([i, j]).value  # length or node_no
        if j == 0:  # first (line-)floor
            if val is not None:
                current_nodes = [attachment_points_lower[int(sheet.get_cell([i, j]).value)]] + \
                                [None for __ in range(num_cols)]
            j += 1
        elif j + 2 < num_cols:
            if val is None:  # ?
                j += 2
            else:
                # We have a line
                line_type_name = sheet.get_cell([i, j + 1]).value

                lower_node = current_nodes[j // 2]

                # gallery
                if j + 4 >= num_cols or sheet.get_cell([i, j + 2]).value is None:

                    upper = attachment_points_upper[val]
                    line_length = None
                    i += 1
                    j = 0
                # other line
                else:
                    upper = BatchNode2D([0, 0])
                    current_nodes[j // 2 + 1] = upper
                    line_length = sheet.get_cell([i, j]).value
                    j += 2

                linelist.append(
                    Line2D(lower_node, upper, target_length=line_length, line_type=line_type_name))
                count += 1

        elif j + 2 >= num_cols:
            j = 0
            i += 1
    return LineSet2D(linelist)


def read_elements(sheet, keyword, len_data=2):
    """
    Return rib/cell_no for the element + data

    -> read_elements(sheet, "AHP", 2) -> [ [rib_no, id, x], ...]
    """

    elements = []
    j = 0
    while j < sheet.ncols():
        if sheet.get_cell([0, j]).value == keyword:
            for i in range(1, sheet.nrows()):
                line = [sheet.get_cell([i, j + k]).value for k in range(len_data)]
                if line[0] is not None:
                    elements.append([i - 1] + line)
            j += len_data
        else:
            j += 1
    return elements


def to_dct(elems, keywords):
    return [{key: value for key, value in zip(keywords, elem)} for elem in elems]


def group(lst, keyword):
    new_lst = []

    def equal(first, second):
        if first.keys() != second.keys():
            return False
        for key in first:
            if key == keyword:
                continue
            if first[key] != second[key]:
                return False

        return True

    def insert(_obj):
        for obj2 in new_lst:
            if equal(_obj, obj2):
                obj2[keyword] += _obj[keyword]
                return

        # nothing found
        new_lst.append(_obj)

    for obj in lst:
        # create a list to group
        obj[keyword] = [obj[keyword]]
        insert(obj)

    return new_lst