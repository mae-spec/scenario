"""Arbres : marronniers et platanes des jardins des Champs-Élysées, des
Tuileries, des quais et de l'esplanade des Invalides (copies liées)."""
from __future__ import annotations

import math
import random

import bmesh
from mathutils import Vector, noise

import geo
from city import RIVER, in_river
from helpers import add_cylinder, instance, object_from_bmesh


def _crown(bm, center, radius, seed, mat):
    res = bmesh.ops.create_icosphere(bm, subdivisions=3, radius=radius)
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    for v in res["verts"]:
        d = noise.noise(v.co * (1.6 / radius) + off)
        v.co *= 1.0 + 0.28 * d
        v.co.z *= 0.85
        v.co += Vector(center)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = mat


def tree_prototypes(coll, M):
    protos = []
    rnd = random.Random(3)
    for k in range(4):
        bm = bmesh.new()
        h = 4.0 + k * 0.6
        add_cylinder(bm, (0, 0, h / 2), 0.32, h, 8, 0, radius_top=0.22)
        crown_r = 4.2 + 0.5 * k
        _crown(bm, (0, 0, h + crown_r * 0.9), crown_r, k, 1)
        for j in range(3):
            a = rnd.uniform(0, math.tau)
            _crown(bm, (2.4 * math.cos(a), 2.4 * math.sin(a),
                        h + crown_r * rnd.uniform(0.5, 1.1)),
                   crown_r * 0.62, k * 10 + j, 1)
        o = object_from_bmesh(f"PROTO_ARBRE_{k}", bm, coll, location=(0, 0, -200))
        o.data.materials.append(M["ecorce"])
        o.data.materials.append(M["feuillage"])
        o.hide_render = True
        o.hide_viewport = True
        protos.append(o)
    return protos


def _ok(u, v):
    if in_river(u, v, 10):
        return False
    if abs(u) < geo.PLACE_HALF_U + 8 and abs(v) < geo.PLACE_HALF_V + 40:
        return False
    if -690 < u < -370 and -340 < v < -90:
        return False  # Grand et Petit Palais
    return True


def plant(coll, M, seed=1925):
    rnd = random.Random(seed)
    protos = tree_prototypes(coll, M)
    pts = []

    def grid(u0, u1, v0, v1, step, keep=0.9, jitter=2.0):
        u = u0
        while u <= u1:
            v = v0
            while v <= v1:
                if rnd.random() < keep:
                    pts.append((u + rnd.uniform(-jitter, jitter),
                                v + rnd.uniform(-jitter, jitter), 0.0))
                v += step
            u += step

    def row(p0, p1, step, z=0.0):
        a, b = Vector(p0), Vector(p1)
        n = int((b - a).length / step)
        for i in range(n + 1):
            p = a.lerp(b, i / max(1, n))
            pts.append((p.x, p.y, z))

    hw = geo.CHAMPS_ELYSEES_HALF_W
    # Jardins des Champs-Élysées (bosquets autour des pavillons, pelouses)
    w0 = geo.MARLY_U - 15
    grid(-1150, w0, hw + 14, 175, 11, keep=0.75, jitter=3)
    grid(-1150, w0, -230, -hw - 14, 11, keep=0.75, jitter=3)
    for s in (-1, 1):
        row((-1300, s * (hw + 4)), (w0, s * (hw + 4)), 9)
        row((-1300, s * (hw + 10)), (w0, s * (hw + 10)), 9)
    # Tuileries : quinconces de marronniers au-delà du Grand Bassin octogonal
    grid(420, 1150, 32, 86, 9, keep=0.95, jitter=1)
    grid(420, 1150, -86, -32, 9, keep=0.95, jitter=1)
    # alignements sur les terrasses (5 m au-dessus du jardin)
    for s, v in ((1, 98.0), (-1, -98.0)):
        row((250, v), (455, v), 8, z=5.0)
    # Quais (rangées de platanes) et Cours la Reine
    for k, p in enumerate(RIVER[:-1]):
        q = RIVER[k + 1]
        t = (q - p).normalized()
        n = Vector((-t.y, t.x))
        L = (q - p).length
        for i in range(int(L / 9)):
            c = p + t * (i * 9)
            for side, off in ((1, geo.SEINE_WIDTH / 2 + 9),
                              (-1, geo.SEINE_WIDTH / 2 + 9),
                              (1, geo.SEINE_WIDTH / 2 + 20)):
                x = c + n * side * off
                if abs(x.x) < 30:
                    continue  # débouché du pont de la Concorde
                pts.append((x.x, x.y, 0.0))
    # Esplanade des Invalides : quatre rangées dans l'axe
    du, dv = geo.INVALIDES_DOME
    bridge = Vector(geo.PONT_ALEXANDRE_III)
    base = Vector((du, dv + 250))
    axis = (bridge - base)
    axis_n = Vector((-axis.y, axis.x)).normalized()
    for off in (-110, -95, 95, 110):
        row(base + axis_n * off, bridge - axis.normalized() * 90 + axis_n * off,
            10)
    n = 0
    for u, v, z in pts:
        if not _ok(u, v):
            continue
        p = rnd.choice(protos)
        o = instance(p, f"ARBRE_{n:04d}", coll, (u, v, z),
                     rnd.uniform(0, math.tau), rnd.uniform(0.85, 1.25))
        o.hide_viewport = False
        n += 1
    return n
