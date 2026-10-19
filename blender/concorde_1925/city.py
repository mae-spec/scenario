"""Sol, Seine, ponts, aménagement de la place, et décor urbain lointain
(Madeleine, Palais-Bourbon, Invalides, tour Eiffel, Grand Palais, immeubles)."""
from __future__ import annotations

import math
import random

import bmesh
import numpy as np
from mathutils import Vector

import geo
from helpers import (add_box, add_cylinder, add_prism, add_sphere,
                     add_wall_xz, inset_outline, object_from_bmesh)

# --- Seine -------------------------------------------------------------------


def _chaikin(pts, iterations=3):
    for _ in range(iterations):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append(a.lerp(b, 0.25))
            out.append(a.lerp(b, 0.75))
        out.append(pts[-1])
        pts = out
    return pts


RIVER = _chaikin([Vector(geo.latlon_to_place(*p))
                  for p in geo.SEINE_AXIS_LATLON])


_SEG_A = np.array([(p.x, p.y) for p in RIVER[:-1]])
_SEG_B = np.array([(p.x, p.y) for p in RIVER[1:]])
_SEG_D = _SEG_B - _SEG_A
_SEG_L2 = (_SEG_D ** 2).sum(axis=1)
_SEG_N = np.stack([-_SEG_D[:, 1], _SEG_D[:, 0]], axis=1) / np.sqrt(_SEG_L2)[:, None]


def river_query_np(pts: np.ndarray):
    """Version vectorisée : pts (n, 2) → distances (n,), projetés (n, 2), normales (n, 2)."""
    rel = pts[:, None, :] - _SEG_A[None, :, :]
    t = np.clip((rel * _SEG_D[None]).sum(axis=2) / _SEG_L2[None], 0.0, 1.0)
    q = _SEG_A[None] + t[..., None] * _SEG_D[None]
    d = np.sqrt(((pts[:, None, :] - q) ** 2).sum(axis=2))
    k = d.argmin(axis=1)
    idx = np.arange(len(pts))
    return d[idx, k], q[idx, k], _SEG_N[k]


def river_query(u: float, v: float):
    """Distance à l'axe de la Seine, point le plus proche, normale (rive droite)."""
    d, q, n = river_query_np(np.array([[u, v]]))
    return float(d[0]), Vector(q[0]), Vector(n[0])


def in_river(u, v, margin=0.0):
    return river_query(u, v)[0] < geo.SEINE_WIDTH / 2 + margin


def ground_and_river(coll, M, extent=(-2400, 1400, -2300, 1300), cell=8.0):
    """Sol de la ville (z = 0) découpé exactement le long des parapets."""
    u0, u1, v0, v1 = extent
    bm = bmesh.new()
    nu, nv = int((u1 - u0) / cell), int((v1 - v0) / cell)
    half = geo.SEINE_WIDTH / 2
    grid = []
    inside = []
    us = u0 + np.arange(nu + 1) * cell
    for j in range(nv + 1):
        v = v0 + j * cell
        pts = np.stack([us, np.full_like(us, v)], axis=1)
        d, q, n = river_query_np(pts)
        is_in = d < half
        side = np.where(((pts - q) * n).sum(axis=1) >= 0, 1.0, -1.0)
        snapped = q + n * (side * half)[:, None]
        pts = np.where(is_in[:, None], snapped, pts)
        grid.append([bm.verts.new((x, y, 0.0)) for x, y in pts])
        inside.append(is_in.tolist())
    for j in range(nv):
        for i in range(nu):
            flags = (inside[j][i], inside[j][i + 1], inside[j + 1][i + 1],
                     inside[j + 1][i])
            if all(flags):
                continue
            # cellule dont le centre tombe dans le lit : on l'abandonne aussi
            us = [grid[j][i].co, grid[j][i + 1].co, grid[j + 1][i + 1].co,
                  grid[j + 1][i].co]
            c = sum(us, Vector()) / 4
            if any(flags) and in_river(c.x, c.y, -0.5):
                continue
            try:
                bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1],
                              grid[j + 1][i]))
            except ValueError:
                pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.05)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    object_from_bmesh("SOL_CHAUSSEE", bm, coll, M["chaussee"])

    # eau, murs de quai et parapets
    w = bmesh.new()
    left = [q + n * half for q, n in _offsets()]
    right = [q - n * half for q, n in _offsets()]
    verts_l = [w.verts.new((p.x, p.y, geo.SEINE_LEVEL)) for p in left]
    verts_r = [w.verts.new((p.x, p.y, geo.SEINE_LEVEL)) for p in right]
    for k in range(len(left) - 1):
        w.faces.new((verts_l[k], verts_r[k], verts_r[k + 1], verts_l[k + 1]))
    object_from_bmesh("SEINE", w, coll, M["seine"])
    q = bmesh.new()
    for bank in (left, right):
        for a, b in zip(bank, bank[1:]):
            mid = (a + b) / 2
            ang = math.atan2(b.y - a.y, b.x - a.x)
            L = (b - a).length + 0.05
            add_box(q, (mid.x, mid.y, (geo.SEINE_LEVEL - 1 + 0.0) / 2),
                    (L, 0.8, -geo.SEINE_LEVEL + 1), 0, ang)
            add_box(q, (mid.x, mid.y, 0.5), (L, 0.6, 1.0), 0, ang)
    object_from_bmesh("QUAIS_PARAPETS", q, coll, M["pierre"])


def _offsets():
    out = []
    for k, p in enumerate(RIVER):
        a = RIVER[max(0, k - 1)]
        b = RIVER[min(len(RIVER) - 1, k + 1)]
        t = (b - a).normalized()
        out.append((p, Vector((-t.y, t.x))))
    return out


def bridge(coll, M, name, center, axis_angle, length, width, arches=5,
           pylons=False):
    """Pont en maçonnerie à arches surbaissées (repère place)."""
    bm = bmesh.new()
    zt = 0.0
    add_box(bm, (0, 0, zt - 0.6), (length, width, 1.2), 0)
    span = length / arches
    for k in range(arches + 1):
        x = -length / 2 + k * span
        add_box(bm, (x, 0, (geo.SEINE_LEVEL + zt - 1) / 2),
                (3.2 if 0 < k < arches else 6.0, width + 1.0,
                 zt - 1 - geo.SEINE_LEVEL), 0)
    for k in range(arches):
        x0 = -length / 2 + k * span + 1.6
        x1 = x0 + span - 3.2
        pts = [(x0, geo.SEINE_LEVEL + 3.0)]
        for i in range(1, 12):
            t = i / 12
            pts.append((x0 + (x1 - x0) * t,
                        geo.SEINE_LEVEL + 3.0 + 5.0 * math.sin(math.pi * t)))
        pts += [(x1, geo.SEINE_LEVEL + 3.0), (x1, zt - 1.2), (x0, zt - 1.2)]
        add_wall_xz(bm, pts, -width / 2 - 0.3, width / 2 + 0.3, 0)
    for s in (-1, 1):
        add_box(bm, (0, s * (width / 2 - 0.3), zt + 0.55), (length, 0.6, 1.1),
                0)
    if pylons:
        for sx in (-1, 1):
            for sy in (-1, 1):
                p = (sx * (length / 2 + 4), sy * (width / 2 + 3))
                add_box(bm, (*p, 9.0), (4.0, 4.0, 18.0), 0)
                add_sphere(bm, (p[0], p[1], 20.0), 1.4, 1, 10, (1, 1, 1.8))
    obj = object_from_bmesh(name, bm, coll, location=(*center, 0),
                            rotation_z=axis_angle)
    obj.data.materials.append(M["pierre_claire"])
    obj.data.materials.append(M["dorure"])
    return obj


def bridges(coll, M):
    # Pont de la Concorde (Perronet, 1791), dans l'axe rue Royale / Palais-Bourbon
    d0, q0, n0 = river_query(0.0, -220.0)
    bridge(coll, M, "PONT_DE_LA_CONCORDE", (0.0, q0.y), math.pi / 2,
           geo.SEINE_WIDTH + 8, geo.PONT_CONCORDE_WIDTH)
    d1, q1, n1 = river_query(*geo.PONT_ALEXANDRE_III)
    bridge(coll, M, "PONT_ALEXANDRE_III", (q1.x, q1.y),
           math.atan2(n1.y, n1.x), geo.SEINE_WIDTH + 8, 40.0, arches=1,
           pylons=True)


# --- La place ---------------------------------------------------------------


def place_layout(coll, M):
    """Terre-pleins, balustrades, refuges ; renvoie les points d'éclairage."""
    outer = geo.PLACE_INNER
    inner = inset_outline(outer, 10.0)
    bm = bmesh.new()   # 0 trottoir, 1 pierre (balustrades)
    lamp_pts, rostral_pts, vertices, baluster_pts = [], [], [], []
    gaps = {3: 17.0, 7: 17.0}      # rue Royale au nord, pont au sud
    skip = {1, 5}                  # côtés est (Tuileries) et ouest (Champs-Élysées)
    for i in range(8):
        a0, a1 = Vector(outer[i]), Vector(outer[(i + 1) % 8])
        b0, b1 = Vector(inner[i]), Vector(inner[(i + 1) % 8])
        vertices.append(a0)
        if i in skip:
            continue
        pieces = [(0.0, 1.0)]
        if i in gaps:
            L = (a1 - a0).length
            g = gaps[i] / L
            pieces = [(0.0, 0.5 - g), (0.5 + g, 1.0)]
        for t0, t1 in pieces:
            p0, p1 = a0.lerp(a1, t0), a0.lerp(a1, t1)
            q0, q1 = b0.lerp(b1, t0), b0.lerp(b1, t1)
            add_prism(bm, [tuple(p0), tuple(p1), tuple(q1), tuple(q0)], 0.0,
                      0.15, 0)
            seg = (p1 - p0)
            L = seg.length
            ang = math.atan2(seg.y, seg.x)
            nrm = (q0 - p0).normalized() * 0.4
            mid = (p0 + p1) / 2 + nrm
            add_box(bm, (mid.x, mid.y, 0.2), (L, 0.5, 0.25), 1, ang)
            add_box(bm, (mid.x, mid.y, 1.08), (L, 0.55, 0.2), 1, ang)
            for k in range(int(L / 0.3)):
                pt = p0.lerp(p1, (k + 0.5) / int(L / 0.3)) + nrm
                baluster_pts.append((pt.x, pt.y))
            n_lamp = max(2, int(L / 13))
            for k in range(n_lamp):
                pt = q0.lerp(q1, (k + 0.5) / n_lamp) + (p0 - q0).normalized() * 1.5
                lamp_pts.append((pt.x, pt.y))
            for t in (0.15, 0.85) if L > 40 else (0.5,):
                pt = p0.lerp(p1, t) + nrm * 3.0
                rostral_pts.append((pt.x, pt.y))
    # refuge de l'obélisque et refuges des fontaines
    add_prism(bm, [(-17, -12), (17, -12), (17, 12), (-17, 12)], 0.0, 0.15, 0)
    for k in range(12):
        a = k * math.tau / 12
        lamp_pts.append((15.5 * math.cos(a), 10.5 * math.sin(a)))
    for v in (geo.FOUNTAIN_NORTH_V, geo.FOUNTAIN_SOUTH_V):
        ring = [(16.0 * math.cos(a), v + 13.0 * math.sin(a))
                for a in [k * math.tau / 48 for k in range(48)]]
        add_prism(bm, ring, 0.0, 0.15, 0)
        for k in range(10):
            a = k * math.tau / 10 + 0.3
            lamp_pts.append((14.5 * math.cos(a), v + 11.5 * math.sin(a)))
    # trottoirs devant les palais de Gabriel et le long des Tuileries
    add_box(bm, (0, geo.GABRIEL_FACADE_V - 4.0, 0.075), (440, 8.0, 0.15), 0)
    for s in (-1, 1):
        add_box(bm, (geo.PLACE_HALF_U + 4, s * 70, 0.075), (8, 70, 0.15), 0)
    obj = object_from_bmesh("TERRE_PLEINS_BALUSTRADES", bm, coll)
    obj.data.materials.append(M["trottoir"])
    obj.data.materials.append(M["pierre"])
    b = bmesh.new()
    for x, y in baluster_pts:
        add_cylinder(b, (x, y, 0.62), 0.1, 0.75, 6, 0, radius_top=0.07)
    object_from_bmesh("BALUSTRES", b, coll, M["pierre"])
    return lamp_pts, rostral_pts, vertices


def tuileries_entrance(coll, M):
    """Terrasses du Jeu de Paume et de l'Orangerie, grille et Renommées."""
    bm = bmesh.new()  # 0 pierre, 1 gravier, 2 vitre, 3 ardoise
    x0 = geo.PLACE_HALF_U + 8
    for s, (cu, cv) in ((1, geo.JEU_DE_PAUME), (-1, geo.ORANGERIE)):
        v_in, v_out = s * 26, s * 110
        add_box(bm, (x0 + 175, (v_in + v_out) / 2, 2.5),
                (350, abs(v_out - v_in), 5.0), 0)
        add_box(bm, (x0 + 175, (v_in + v_out) / 2, 5.02),
                (348, abs(v_out - v_in) - 2, 0.04), 1)
        # bâtiment (Jeu de Paume / Orangerie) : 100 × 18 m
        add_box(bm, (cu, cv, 5 + 6.0), (100, 18, 12.0), 0)
        add_prism(bm, [(cu - 50, cv - 9), (cu + 50, cv - 9), (cu + 50, cv + 9),
                       (cu - 50, cv + 9)], 17.0, 20.0, 3,
                  top_outline=[(cu - 47, cv - 2), (cu + 47, cv - 2),
                               (cu + 47, cv + 2), (cu - 47, cv + 2)])
        for k in range(12):
            add_box(bm, (cu - 44 + k * 8, cv - s * 9.05, 11.0),
                    (2.4, 0.1, 6.5), 2)
        # pilier de la grille portant une Renommée de Coysevox
        add_box(bm, (x0 + 2, s * 20, 3.0), (3.0, 3.0, 6.0), 0)
        add_sphere(bm, (x0 + 2, s * 20, 7.5), 1.2, 0, 10, (1.6, 0.8, 1.0))
        add_box(bm, (x0 + 2, s * 20 + s * 0.4, 9.0), (0.5, 3.4, 1.6), 0)
    add_box(bm, (x0 + 700, 0, -0.05), (1400, 52, 0.1), 1)  # allée centrale
    obj = object_from_bmesh("TUILERIES_TERRASSES", bm, coll)
    for m in (M["pierre_claire"], M["gravier"], M["vitre"], M["ardoise"]):
        obj.data.materials.append(m)


def marly_horses(coll, M):
    """Chevaux de Marly (Coustou) à l'entrée des Champs-Élysées."""
    bm = bmesh.new()
    for s in (-1, 1):
        x, y = -geo.PLACE_HALF_U - 4, s * (geo.CHAMPS_ELYSEES_HALF_W + 4)
        add_box(bm, (x, y, 2.5), (5.0, 7.0, 5.0), 0)
        add_box(bm, (x, y, 5.15), (5.6, 7.6, 0.3), 0)
        add_sphere(bm, (x, y, 7.0), 1.1, 0, 12, (1.0, 2.4, 1.1))      # corps
        add_sphere(bm, (x, y - s * 2.2, 8.4), 0.6, 0, 10, (0.8, 1.4, 1.0))
        for dy in (-1.3, 1.3):
            add_cylinder(bm, (x, y + dy, 5.9), 0.25, 1.4, 6, 0)
        add_sphere(bm, (x + 1.3, y + s * 1.2, 7.0), 0.5, 0, 8, (0.8, 0.8, 2.0))
    obj = object_from_bmesh("CHEVAUX_DE_MARLY", bm, coll, M["pierre_claire"])
    return obj


# --- Monuments lointains -----------------------------------------------------


def _classical_portico(bm, cx, cy, width, n_cols, col_h, base_h, depth,
                       facing=1, mat=0):
    """Portique à colonnes + fronton, face vers +v (facing=1) ou -v (-1)."""
    front = cy + facing * depth / 2
    add_box(bm, (cx, cy, base_h / 2), (width + 6, depth + 6, base_h), mat)
    step = width / (n_cols - 1)
    for k in range(n_cols):
        add_cylinder(bm, (cx - width / 2 + k * step, front - facing * 1.2,
                          base_h + col_h / 2), 0.9, col_h, 12, mat,
                     radius_top=0.8)
    zt = base_h + col_h
    add_box(bm, (cx, cy, zt + 1.4), (width + 3, depth + 1, 2.8), mat)
    add_wall_xz(bm, [(cx - width / 2 - 1.5, zt + 2.8),
                     (cx + width / 2 + 1.5, zt + 2.8), (cx, zt + 2.8 + width * 0.2)],
                front - facing * 2.5, front + facing * 0.3, mat)


def landmarks(coll, M):
    # La Madeleine (temple corinthien, 52 colonnes) au bout de la rue Royale
    bm = bmesh.new()
    cy = geo.MADELEINE_V
    _classical_portico(bm, 0, cy - 40, 36, 8, 19.5, 7.0, 22, facing=-1)
    add_box(bm, (0, cy, 7 + 12), (34, 80, 24), 0)
    for s in (-1, 1):
        for k in range(16):
            add_cylinder(bm, (s * 19.5, cy - 48 + k * 6.3, 7 + 9.75), 0.9, 19.5,
                         10, 0)
    add_prism(bm, [(-21, cy - 50), (21, cy - 50), (21, cy + 52), (-21, cy + 52)],
              7 + 22.3, 7 + 25, 1,
              top_outline=[(-2, cy - 50), (2, cy - 50), (2, cy + 52),
                           (-2, cy + 52)])
    obj = object_from_bmesh("EGLISE_DE_LA_MADELEINE", bm, coll)
    obj.data.materials.append(M["pierre"])
    obj.data.materials.append(M["zinc"])

    # Palais-Bourbon : portique de Poyet (1806), 12 colonnes face au pont
    bm = bmesh.new()
    pv = geo.PALAIS_BOURBON_PORTICO_V
    _classical_portico(bm, 0, pv - 8, 46, 12, 15.0, 6.0, 16, facing=1)
    add_box(bm, (0, pv - 70, 11), (60, 110, 22), 0)
    for s in (-1, 1):
        add_box(bm, (s * 70, pv - 50, 8), (80, 70, 16), 0)
        add_prism(bm, [(s * 30, pv - 85), (s * 110, pv - 85), (s * 110, pv - 15),
                       (s * 30, pv - 15)], 16, 20, 1,
                  top_outline=[(s * 33, pv - 82), (s * 107, pv - 82),
                               (s * 107, pv - 18), (s * 33, pv - 18)])
    for k in range(10):  # statues assises devant les marches
        add_sphere(bm, (-20 + k * 4.4, pv + 9, 4.2), 0.8, 0, 8, (1, 1, 1.7))
    obj = object_from_bmesh("PALAIS_BOURBON", bm, coll)
    obj.data.materials.append(M["pierre"])
    obj.data.materials.append(M["ardoise"])

    # Dôme des Invalides (Hardouin-Mansart) : 107 m
    du, dv = geo.INVALIDES_DOME
    bm = bmesh.new()
    add_box(bm, (du, dv, 15), (60, 60, 30), 0)
    _classical_portico(bm, du, dv + 26, 22, 6, 13, 3, 10, facing=1)
    add_cylinder(bm, (du, dv, 30 + 13), 15.5, 26, 32, 0)
    for k in range(24):
        a = k * math.tau / 24
        add_cylinder(bm, (du + 16.6 * math.cos(a), dv + 16.6 * math.sin(a),
                          30 + 12), 0.7, 22, 8, 0)
    add_cylinder(bm, (du, dv, 57.5), 16.5, 3, 32, 0)
    add_sphere(bm, (du, dv, 59), 15.5, 2, 32, (1, 1, 1.25))
    add_cylinder(bm, (du, dv, 83), 3.0, 10, 12, 2, radius_top=2.2)
    add_cylinder(bm, (du, dv, 95), 1.6, 14, 8, 2, radius_top=0.1)
    # corps de l'Hôtel des Invalides, au nord du dôme
    add_box(bm, (du, dv + 140, 11), (390, 200, 22), 0)
    add_prism(bm, [(du - 195, dv + 40), (du + 195, dv + 40),
                   (du + 195, dv + 240), (du - 195, dv + 240)], 22, 28, 1,
              top_outline=[(du - 190, dv + 45), (du + 190, dv + 45),
                           (du + 190, dv + 235), (du - 190, dv + 235)])
    obj = object_from_bmesh("INVALIDES_DOME", bm, coll)
    for m in (M["pierre"], M["ardoise"], M["dorure"]):
        obj.data.materials.append(m)
    # la dorure du dôme, ternie en 1925 (redorée en 1937 puis en 1989)
    from materials import principled
    obj.data.materials[1] = principled("PLOMB_DORE_TERNI", (0.23, 0.2, 0.14),
                                       0.45, 0.6, variation=0.4)

    # Tour Eiffel (1889) : 300 m + antenne, 312 m en 1925
    eu, ev = geo.TOUR_EIFFEL
    bm = bmesh.new()
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_prism(bm, [(sx * 62, sy * 62), (sx * 47, sy * 62),
                           (sx * 47, sy * 47), (sx * 62, sy * 47)][::sx * sy],
                      0, 57, 0,
                      top_outline=[(sx * 36, sy * 36), (sx * 26, sy * 36),
                                   (sx * 26, sy * 26), (sx * 36, sy * 26)
                                   ][::sx * sy])
            add_prism(bm, [(sx * 34, sy * 34), (sx * 22, sy * 34),
                           (sx * 22, sy * 22), (sx * 34, sy * 22)][::sx * sy],
                      60, 115, 0,
                      top_outline=[(sx * 19, sy * 19), (sx * 9, sy * 19),
                                   (sx * 9, sy * 9), (sx * 19, sy * 9)
                                   ][::sx * sy])
    add_box(bm, (0, 0, 58.5), (72, 72, 4), 0)
    add_box(bm, (0, 0, 116.5), (40, 40, 3), 0)
    add_prism(bm, [(-19, -19), (19, -19), (19, 19), (-19, 19)], 118, 276, 0,
              top_outline=[(-5, -5), (5, -5), (5, 5), (-5, 5)])
    add_box(bm, (0, 0, 278), (16, 16, 6), 0)
    add_cylinder(bm, (0, 0, 295), 0.6, 30, 6, 0, radius_top=0.2)
    object_from_bmesh("TOUR_EIFFEL", bm, coll, M["metal_eiffel"],
                      location=(eu, ev, 0),
                      rotation_z=math.radians(geo.AXIS_AZIMUTH_DEG + 45))

    # Grand Palais (1900) : nef de verre, et Petit Palais
    gu, gv = geo.GRAND_PALAIS
    bm = bmesh.new()
    add_box(bm, (gu, gv, 10), (60, 230, 20), 0)
    for k in range(24):
        a0 = math.pi * k / 24
        a1 = math.pi * (k + 1) / 24
        p = [(gu + 26 * math.cos(a0), 20 + 18 * math.sin(a0)),
             (gu + 26 * math.cos(a1), 20 + 18 * math.sin(a1)),
             (gu + 25.5 * math.cos(a1), 20 + 17.5 * math.sin(a1)),
             (gu + 25.5 * math.cos(a0), 20 + 17.5 * math.sin(a0))]
        add_wall_xz(bm, p, gv - 110, gv + 110, 1)
    add_cylinder(bm, (gu, gv - 30, 30), 18, 20, 24, 0)
    add_sphere(bm, (gu, gv - 30, 40), 18, 1, 24, (1, 1, 0.9))
    add_cylinder(bm, (gu, gv - 30, 58), 1.0, 10, 8, 0)
    pu, pv2 = geo.PETIT_PALAIS
    add_box(bm, (pu, pv2, 9), (50, 150, 18), 0)
    add_sphere(bm, (pu, pv2, 18), 9, 2, 16, (1, 1, 1.3))
    obj = object_from_bmesh("GRAND_ET_PETIT_PALAIS", bm, coll)
    for m in (M["pierre_claire"], M["verriere"], M["ardoise"]):
        obj.data.materials.append(m)


# --- Tissu urbain -----------------------------------------------------------


def _free_for_building(u, v, w, d):
    corners = [(u + a * w / 2, v + b * d / 2) for a in (-1, 0, 1)
               for b in (-1, 0, 1)]
    for x, y in corners:
        if in_river(x, y, 30):
            return False
        # place, jardins des Champs-Élysées, Tuileries, esplanade des Invalides
        if -720 < x < 1000 and -150 < y < geo.GABRIEL_FACADE_V - 6 and not (
                x > 700 and y > 110):
            return False
        if x > 150 and -170 < y < geo.RIVOLI_FACADE_V and x < 1100:
            return False
        if x < -150 and abs(y) < 210 and x > -1200:
            return False   # Champs-Élysées et leurs jardins
        if -110 < x < 110 and geo.GABRIEL_FACADE_V < y < 680:
            if abs(x) < 70 and y < 470:
                if abs(x) < 15:
                    return False
            if abs(x) < 50 and y > 470:
                return False
        if -680 < x < -380 and -330 < y < -100:
            return False   # Grand et Petit Palais
        du, dv = geo.INVALIDES_DOME
        if abs(x - du) < 260 and dv - 80 < y < dv + 250:
            return False
        if abs(x - du + 0.45 * (y - dv)) < 160 and dv + 250 < y < -280:
            return False   # esplanade
        if abs(x - 90) < 160 and -600 < y < -260 and abs(x) < 130:
            return False   # place du Palais-Bourbon
        if (x + 1418) ** 2 + (y + 1575) ** 2 < 330 ** 2:
            return False   # Champ-de-Mars / Trocadéro
    if (-110 < u < 110 and geo.GABRIEL_FACADE_V - 26 < v
            < geo.GABRIEL_FACADE_V + geo.GABRIEL_DEPTH + 10):
        return False       # palais de Gabriel (construits à part)
    return True


def city_blocks(coll, M, seed=1925):
    """Îlots haussmanniens et classiques (R+5, combles à la Mansart)."""
    rnd = random.Random(seed)
    bm = bmesh.new()  # 0 façade, 1 façade sombre, 2 zinc
    placed = 0
    # Rue Royale : deux fronts bâtis continus jusqu'à la Madeleine
    for s in (-1, 1):
        v = geo.GABRIEL_FACADE_V + geo.GABRIEL_DEPTH + 2
        while v < 470:
            d = rnd.uniform(18, 32)
            _block(bm, s * (geo.RUE_ROYALE_HALF_W + 18), v + d / 2, 36, d,
                   rnd.uniform(19, 22), rnd)
            v += d + 0.3
    # Rue de Rivoli (arcades) au nord des Tuileries
    u = 130
    while u < 1300:
        w = rnd.uniform(30, 45)
        _block(bm, u + w / 2, geo.RIVOLI_FACADE_V + 22, w, 44, 21.0, rnd,
               mansard=True)
        u += w + 0.3
    # Palais de Gabriel : immeubles derrière, rue Boissy-d'Anglas, Saint-Florentin
    for cu in (-140.0, 140.0):
        _block(bm, cu, geo.GABRIEL_FACADE_V + 40, 50, 75, 20, rnd)
    # Remplissage par anneaux concentriques
    for ring in range(1, 46):
        r = 150 + ring * 55
        n = int(math.tau * r / 60)
        for k in range(n):
            a = k * math.tau / n + rnd.uniform(-0.01, 0.01)
            u = r * math.cos(a) + rnd.uniform(-10, 10)
            v = r * math.sin(a) + rnd.uniform(-10, 10)
            w, d = rnd.uniform(35, 60), rnd.uniform(35, 60)
            if not _free_for_building(u, v, w, d):
                continue
            _block(bm, u, v, w, d, rnd.uniform(17, 24), rnd)
            placed += 1
    obj = object_from_bmesh("ILOTS_URBAINS", bm, coll)
    for m in (M["facade"], M["facade_sombre"], M["zinc"]):
        obj.data.materials.append(m)
    return placed


def _block(bm, cu, cv, w, d, h, rnd, mansard=True):
    m = rnd.choice((0, 0, 1))
    add_box(bm, (cu, cv, h / 2), (w, d, h), m)
    if mansard:
        o = [(cu - w / 2, cv - d / 2), (cu + w / 2, cv - d / 2),
             (cu + w / 2, cv + d / 2), (cu - w / 2, cv + d / 2)]
        t = [(cu - w / 2 + 2.5, cv - d / 2 + 2.5), (cu + w / 2 - 2.5, cv - d / 2 + 2.5),
             (cu + w / 2 - 2.5, cv + d / 2 - 2.5), (cu - w / 2 + 2.5, cv + d / 2 - 2.5)]
        add_prism(bm, o, h, h + 5.5, 2, top_outline=t)
        for k in range(int(w / 9)):
            add_box(bm, (cu - w / 2 + 4 + k * 9, cv + rnd.uniform(-d / 4, d / 4),
                         h + 6.5), (1.2, 0.6, 2.4), 1)
