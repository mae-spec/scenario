"""Outils de construction : collections, maillages simples, instanciation."""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

_root = {"frame": None}


def set_frame(obj: bpy.types.Object) -> None:
    """Objet vide portant la rotation du repère place → nord géographique."""
    _root["frame"] = obj


def collection(name: str, parent: bpy.types.Collection | None = None
               ) -> bpy.types.Collection:
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(coll)
    return coll


def link(obj: bpy.types.Object, coll: bpy.types.Collection,
         in_place_frame: bool = True) -> bpy.types.Object:
    coll.objects.link(obj)
    if in_place_frame and _root["frame"] is not None and obj.parent is None:
        obj.parent = _root["frame"]
    return obj


def object_from_bmesh(name: str, bm: bmesh.types.BMesh, coll, mat=None,
                      location=(0, 0, 0), rotation_z: float = 0.0,
                      smooth: bool = False) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    if mat is not None:
        me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    obj.location = location
    obj.rotation_euler.z = rotation_z
    return link(obj, coll)


def instance(src: bpy.types.Object, name: str, coll, location,
             rotation_z: float = 0.0, scale: float | tuple = 1.0
             ) -> bpy.types.Object:
    """Copie liée (même maillage) : léger en mémoire, modifiable d'un coup."""
    obj = bpy.data.objects.new(name, src.data)
    obj.location = location
    obj.rotation_euler.z = rotation_z
    obj.scale = (scale,) * 3 if isinstance(scale, (int, float)) else scale
    return link(obj, coll)


def join(objs: list[bpy.types.Object], name: str) -> bpy.types.Object:
    """Fusionne des objets (même parent) en un seul maillage."""
    objs = [o for o in objs if o is not None]
    base = objs[0]
    bm = bmesh.new()
    mats: list = []
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        offset = len(mats)
        for m in o.data.materials:
            mats.append(m)
        for f in tmp.faces:
            f.material_index += offset
        local = base.matrix_basis.inverted() @ o.matrix_basis
        bmesh.ops.transform(tmp, matrix=local, verts=tmp.verts)
        me_tmp = bpy.data.meshes.new("_tmp")
        tmp.to_mesh(me_tmp)
        tmp.free()
        bm.from_mesh(me_tmp)
        bpy.data.meshes.remove(me_tmp)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    obj = bpy.data.objects.new(name, me)
    obj.matrix_basis = base.matrix_basis.copy()
    obj.parent = base.parent
    for c in base.users_collection:
        c.objects.link(obj)
    for o in objs:
        data = o.data
        bpy.data.objects.remove(o)
        if data.users == 0:
            bpy.data.meshes.remove(data)
    return obj


# --- Primitives bmesh (cumulables dans un même bmesh) -----------------------
# Les opérateurs bmesh parcourent tout le maillage cible : on construit chaque
# primitive dans un petit bmesh temporaire, puis on la recopie.

def _emit(bm, tmp, mat_index: int, matrix=None):
    if matrix is not None:
        bmesh.ops.transform(tmp, matrix=matrix, verts=tmp.verts)
    remap = {v: bm.verts.new(v.co) for v in tmp.verts}
    for f in tmp.faces:
        nf = bm.faces.new([remap[v] for v in f.verts])
        nf.material_index = mat_index
        nf.smooth = f.smooth
    tmp.free()
    return list(remap.values())


def add_box(bm, center, size, mat_index: int = 0, rot_z: float = 0.0,
            rot_y: float = 0.0):
    sx, sy, sz = size
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    m = (Matrix.Translation(Vector(center)) @ Matrix.Rotation(rot_z, 4, "Z")
         @ Matrix.Rotation(rot_y, 4, "Y") @ Matrix.Diagonal((sx, sy, sz, 1.0)))
    return _emit(bm, tmp, mat_index, m)


def add_cylinder(bm, center, radius, depth, segments: int = 16,
                 mat_index: int = 0, radius_top: float | None = None,
                 axis: str = "Z", caps: bool = True):
    rt = radius if radius_top is None else radius_top
    tmp = bmesh.new()
    bmesh.ops.create_cone(tmp, cap_ends=caps, cap_tris=False,
                          segments=segments, radius1=radius, radius2=rt,
                          depth=depth)
    rot = {"Z": Matrix.Identity(4),
           "X": Matrix.Rotation(math.pi / 2, 4, "Y"),
           "Y": Matrix.Rotation(math.pi / 2, 4, "X")}[axis]
    return _emit(bm, tmp, mat_index, Matrix.Translation(Vector(center)) @ rot)


def add_sphere(bm, center, radius, mat_index: int = 0, segments: int = 12,
               scale=(1.0, 1.0, 1.0)):
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=segments,
                              v_segments=max(6, segments // 2), radius=radius)
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*scale, 1.0))
    return _emit(bm, tmp, mat_index, m)


def add_prism(bm, outline, z0: float, z1: float, mat_index: int = 0,
              top_outline=None):
    """Extrusion d'un polygone (liste (x, y)) entre z0 et z1.

    `top_outline` (même nombre de points) permet un toit à la Mansart.
    """
    top = top_outline or outline
    low = [bm.verts.new((x, y, z0)) for x, y in outline]
    high = [bm.verts.new((x, y, z1)) for x, y in top]
    n = len(outline)
    faces = [bm.faces.new(high), bm.faces.new(list(reversed(low)))]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((low[i], low[j], high[j], high[i])))
    for f in faces:
        f.material_index = mat_index
    return faces


def inset_outline(outline, d: float):
    """Décalage vers l'intérieur d'un polygone convexe orienté (sens trigo)."""
    n = len(outline)
    res = []
    for i in range(n):
        p0 = Vector(outline[i - 1])
        p1 = Vector(outline[i])
        p2 = Vector(outline[(i + 1) % n])
        e0 = (p1 - p0).normalized()
        e1 = (p2 - p1).normalized()
        n0 = Vector((-e0.y, e0.x))
        n1 = Vector((-e1.y, e1.x))
        bis = (n0 + n1).normalized()
        k = d / max(0.2, bis.dot(n0))
        q = p1 + bis * k
        res.append((q.x, q.y))
    return res


def octagon(half_u: float, half_v: float, chamfer: float):
    hu, hv, c = half_u, half_v, chamfer
    return [(hu - c, -hv), (hu, -hv + c), (hu, hv - c), (hu - c, hv),
            (-hu + c, hv), (-hu, hv - c), (-hu, -hv + c), (-hu + c, -hv)]


def add_wall_xz(bm, outline_xz, y0: float, y1: float, mat_index: int = 0):
    """Polygone dans le plan vertical XZ (liste (x, z)), épaissi entre y0 et y1."""
    a = [bm.verts.new((x, y0, z)) for x, z in outline_xz]
    b = [bm.verts.new((x, y1, z)) for x, z in outline_xz]
    n = len(outline_xz)
    faces = [bm.faces.new(a), bm.faces.new(list(reversed(b)))]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((a[i], b[i], b[j], a[j])))
    for f in faces:
        f.material_index = mat_index
    return faces


def add_wall_with_openings(bm, x0, x1, y0, y1, z0, z1, openings,
                           mat_index: int = 0):
    """Mur plein percé d'ouvertures rectangulaires [(xa, xb, za, zb), ...]."""
    xs = sorted({x0, x1, *[o[0] for o in openings], *[o[1] for o in openings]})
    for xa, xb in zip(xs, xs[1:]):
        if xb - xa < 1e-4:
            continue
        xm = (xa + xb) / 2
        holes = sorted((o[2], o[3]) for o in openings if o[0] <= xm <= o[1])
        z = z0
        for za, zb in holes + [(z1, z1)]:
            if za - z > 1e-4:
                add_box(bm, (xm, (y0 + y1) / 2, (z + za) / 2),
                        (xb - xa, y1 - y0, za - z), mat_index)
            z = max(z, zb)


def arch_spandrel(x0, x1, xa, xb, z_spring, z_top, segments: int = 12):
    """Contour (x, z) d'un trumeau + écoinçon au-dessus d'une arcade en plein cintre."""
    r = (xb - xa) / 2
    xc = (xa + xb) / 2
    pts = [(x0, z_spring), (xa, z_spring)]
    for i in range(1, segments):
        t = math.pi - math.pi * i / segments
        pts.append((xc + r * math.cos(t), z_spring + r * math.sin(t)))
    pts += [(xb, z_spring), (x1, z_spring), (x1, z_top), (x0, z_top)]
    return pts
