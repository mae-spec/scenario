"""Obélisque, fontaines de Hittorff, statues des villes, candélabres, colonnes rostrales."""
from __future__ import annotations

import math
import random

import bmesh

import geo
from helpers import (add_box, add_cylinder, add_prism, add_sphere, instance,
                     object_from_bmesh)


def obelisk(coll, M):
    bm = bmesh.new()
    # Socle de granit gris (1836) sur emmarchement
    add_box(bm, (0, 0, 0.25), (9.0, 9.0, 0.5), 1)
    add_box(bm, (0, 0, 0.75), (7.6, 7.6, 0.5), 1)
    add_box(bm, (0, 0, 1.5), (5.4, 5.4, 1.0), 1)
    add_box(bm, (0, 0, 2.0 + (geo.OBELISK_PEDESTAL_H - 3.0) / 2),
            (4.2, 4.2, geo.OBELISK_PEDESTAL_H - 3.0), 1)
    add_box(bm, (0, 0, geo.OBELISK_PEDESTAL_H - 0.5), (4.8, 4.8, 1.0), 1)
    # Fût monolithe de syénite rose, pyramidion nu (la coiffe dorée date de 1998)
    z0 = geo.OBELISK_PEDESTAL_H
    b, t = geo.OBELISK_BASE_SIDE / 2, geo.OBELISK_TOP_SIDE / 2
    h = geo.OBELISK_SHAFT_H - 1.8
    sq = [(-b, -b), (b, -b), (b, b), (-b, b)]
    add_prism(bm, sq, z0, z0 + h, 0,
              top_outline=[(-t, -t), (t, -t), (t, t), (-t, t)])
    apex = bm.verts.new((0, 0, z0 + geo.OBELISK_SHAFT_H))
    ring = [bm.verts.new((x, y, z0 + h)) for x, y in
            [(-t, -t), (t, -t), (t, t), (-t, t)]]
    for i in range(4):
        bm.faces.new((ring[i], ring[(i + 1) % 4], apex))
    obj = object_from_bmesh("OBELISQUE_LOUXOR", bm, coll)
    # 0 : fût en syénite rose ; 1 : socle en granit gris de Bretagne
    obj.data.materials.append(M["granit"])
    obj.data.materials.append(_grey_granite())
    # Grille entourant l'obélisque
    railing(coll, M, "GRILLE_OBELISQUE", [(-15, -11), (15, -11), (15, 11),
                                          (-15, 11)], 1.3)
    return obj


def _grey_granite():
    from materials import principled
    return principled("GRANIT_GRIS_SOCLE", (0.28, 0.28, 0.27), 0.55,
                      variation=0.2, bump=0.2, bump_scale=50)


def railing(coll, M, name, outline, height, z=0.15, spacing=0.14):
    """Grille en fonte : barreaux + lisses, sur un contour fermé."""
    bm = bmesh.new()
    n = len(outline)
    for i in range(n):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % n]
        L = math.hypot(x1 - x0, y1 - y0)
        ang = math.atan2(y1 - y0, x1 - x0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        add_box(bm, (cx, cy, z + height - 0.04), (L, 0.06, 0.06), 0, ang)
        add_box(bm, (cx, cy, z + 0.15), (L, 0.06, 0.06), 0, ang)
        k = max(1, int(L / spacing))
        for j in range(k):
            f = (j + 0.5) / k
            add_box(bm, (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f,
                         z + height / 2), (0.025, 0.025, height), 0)
        add_box(bm, (x0, y0, z + height / 2 + 0.1), (0.12, 0.12, height + 0.2),
                0)
    return object_from_bmesh(name, bm, coll, M["fonte"])


def fountain(coll, M, name, v):
    """Fontaine de Hittorff : bassin, piédestal à figures, deux vasques."""
    bm = bmesh.new()
    # 0 bronze, 1 pierre, 2 dorure
    add_cylinder(bm, (0, 0, 0.45), 8.4, 0.9, 64, 1)          # margelle
    add_cylinder(bm, (0, 0, 0.75), 8.6, 0.25, 64, 1)
    add_cylinder(bm, (0, 0, 1.3), 2.6, 2.6, 24, 0, radius_top=2.0)
    for i in range(6):  # tritons et néréides assis autour du piédestal
        a = i * math.tau / 6
        x, y = 3.4 * math.cos(a), 3.4 * math.sin(a)
        add_sphere(bm, (x, y, 1.6), 0.8, 0, 10, (0.9, 0.9, 1.4))
        add_sphere(bm, (x * 0.93, y * 0.93, 2.6), 0.32, 0, 8)
        add_cylinder(bm, (x * 1.15, y * 1.15, 1.1), 0.5, 0.6, 10, 0)
        # dauphins / poissons cracheurs sur la margelle
        a2 = a + math.tau / 12
        add_sphere(bm, (7.4 * math.cos(a2), 7.4 * math.sin(a2), 1.15), 0.45,
                   0, 8, (1.6, 0.8, 0.8))
    add_cylinder(bm, (0, 0, 3.6), 1.2, 2.0, 20, 0, radius_top=0.9)
    # grande vasque
    add_cylinder(bm, (0, 0, 4.75), 0.8, 0.5, 32, 0, radius_top=4.0)
    add_cylinder(bm, (0, 0, 5.1), 4.0, 0.25, 48, 2)
    for i in range(4):  # génies soutenant la petite vasque
        a = i * math.tau / 4 + 0.4
        add_sphere(bm, (0.9 * math.cos(a), 0.9 * math.sin(a), 5.9), 0.42, 0,
                   8, (0.8, 0.8, 1.7))
    add_cylinder(bm, (0, 0, 6.4), 0.55, 1.6, 16, 0)
    add_cylinder(bm, (0, 0, 7.35), 0.4, 0.4, 24, 0, radius_top=1.9)
    add_cylinder(bm, (0, 0, 7.6), 1.9, 0.15, 32, 2)
    add_cylinder(bm, (0, 0, 8.1), 0.25, 0.9, 12, 0, radius_top=0.12)
    obj = object_from_bmesh(name, bm, coll, location=(0, v, 0))
    for m in (M["bronze"], M["pierre_claire"], M["dorure"]):
        obj.data.materials.append(m)
    # Eau : bassin + nappes tombant des vasques
    w = bmesh.new()
    add_cylinder(w, (0, 0, 0.7), 8.0, 0.1, 64, 0)
    add_cylinder(w, (0, 0, 5.2), 3.85, 0.05, 48, 0)
    # nappes et jets : eau transparente
    add_cylinder(w, (0, 0, 2.95), 3.6, 4.4, 48, 1, radius_top=4.1, caps=False)
    add_cylinder(w, (0, 0, 6.35), 1.6, 2.4, 32, 1, radius_top=1.95,
                 caps=False)
    add_cylinder(w, (0, 0, 8.9), 0.08, 1.2, 8, 1, radius_top=0.3, caps=False)
    for i in range(6):  # jets des dauphins vers le centre
        a = i * math.tau / 6 + math.tau / 12
        add_cylinder(w, (6.2 * math.cos(a), 6.2 * math.sin(a), 1.3), 0.06,
                     1.0, 6, 1, radius_top=0.12)
    eau = object_from_bmesh(name + "_EAU", w, coll, location=(0, v, 0))
    eau.data.materials.append(M["eau"])
    eau.data.materials.append(M["nappe"])
    return obj


def statue_pavilion(coll, M, name, x, y, rot):
    """Guérite de Gabriel portant une statue de ville assise (Cortot, Pradier…)."""
    bm = bmesh.new()
    add_box(bm, (0, 0, 2.0), (5.2, 5.2, 4.0), 0)
    add_box(bm, (0, 0, 4.15), (5.8, 5.8, 0.3), 0)
    add_box(bm, (0, 0, 4.6), (4.0, 3.4, 0.6), 0)
    # figure assise couronnée, très simplifiée (lecture en silhouette)
    add_box(bm, (0, 0.2, 5.5), (2.4, 2.2, 1.2), 1)            # siège + genoux
    add_sphere(bm, (0, 0.5, 6.9), 0.9, 1, 10, (1.0, 0.75, 1.6))  # buste drapé
    add_sphere(bm, (0, 0.55, 8.2), 0.38, 1, 10)                # tête
    add_cylinder(bm, (0, 0.55, 8.62), 0.36, 0.35, 10, 1)       # couronne murale
    add_box(bm, (1.1, -0.3, 6.1), (0.5, 1.8, 0.4), 1)          # bras / attribut
    obj = object_from_bmesh(name, bm, coll, location=(x, y, 0), rotation_z=rot)
    obj.data.materials.append(M["pierre_claire"])
    obj.data.materials.append(M["pierre"])
    return obj


def lamp_prototype(coll, M):
    """Candélabre de Hittorff (fût cannelé, lanterne à quatre faces)."""
    bm = bmesh.new()
    add_cylinder(bm, (0, 0, 0.35), 0.38, 0.7, 12, 0, radius_top=0.3)
    add_cylinder(bm, (0, 0, 2.6), 0.16, 3.8, 12, 0, radius_top=0.11)
    add_cylinder(bm, (0, 0, 4.6), 0.2, 0.3, 12, 2)
    add_cylinder(bm, (0, 0, 4.95), 0.1, 0.5, 8, 0)
    add_cylinder(bm, (0, 0, 5.45), 0.18, 0.7, 4, 1, radius_top=0.3)
    add_cylinder(bm, (0, 0, 5.92), 0.36, 0.3, 4, 0, radius_top=0.05)
    add_sphere(bm, (0, 0, 6.15), 0.07, 2, 6)
    obj = object_from_bmesh("PROTO_CANDELABRE_HITTORFF", bm, coll,
                            location=(0, 0, -100))
    for m in (M["fonte"], M["globe"], M["dorure"]):
        obj.data.materials.append(m)
    return obj


def rostral_prototype(coll, M):
    """Colonne rostrale (proues de navires) surmontée d'une lanterne."""
    bm = bmesh.new()
    add_box(bm, (0, 0, 0.9), (1.5, 1.5, 1.8), 0)
    add_cylinder(bm, (0, 0, 5.0), 0.42, 6.4, 16, 0, radius_top=0.36)
    for k in range(3):
        z = 3.0 + k * 1.8
        for i in range(4):
            a = i * math.pi / 2 + k * math.pi / 4
            add_box(bm, (0.6 * math.cos(a), 0.6 * math.sin(a), z),
                    (0.7, 0.18, 0.35), 2, a)
    add_box(bm, (0, 0, 8.35), (1.1, 1.1, 0.3), 0)
    for i in range(4):
        a = i * math.pi / 2
        add_cylinder(bm, (0.45 * math.cos(a), 0.45 * math.sin(a), 9.0), 0.17,
                     0.6, 4, 1, radius_top=0.24)
    add_cylinder(bm, (0, 0, 9.0), 0.2, 1.2, 8, 0)
    obj = object_from_bmesh("PROTO_COLONNE_ROSTRALE", bm, coll,
                            location=(0, 0, -100))
    for m in (M["fonte"], M["globe"], M["dorure"]):
        obj.data.materials.append(m)
    return obj


def street_furniture(coll, M, island_specs, perimeter_points):
    """Dispose candélabres et colonnes rostrales comme sur la carte postale."""
    lamp = lamp_prototype(coll, M)
    rostral = rostral_prototype(coll, M)
    n = 0
    for pts in island_specs:
        for x, y in pts:
            instance(lamp, f"CANDELABRE_{n:03d}", coll, (x, y, 0.15))
            n += 1
    for i, (x, y) in enumerate(perimeter_points):
        instance(rostral, f"COLONNE_ROSTRALE_{i:02d}", coll, (x, y, 0.15))
    return lamp, rostral


def scatter_people(coll, M, zones, count, seed=7):
    """Passants en silhouette (manteaux sombres, chapeaux) sur les trottoirs."""
    rnd = random.Random(seed)
    protos = []
    for k in range(3):
        bm = bmesh.new()
        h = 1.62 + 0.08 * k
        add_cylinder(bm, (0, 0, 0.45), 0.2, 0.9, 8, 0, radius_top=0.22)
        add_cylinder(bm, (0, 0, 1.1), 0.24, 0.6, 8, 0, radius_top=0.2)
        add_sphere(bm, (0, 0, h - 0.13), 0.11, 1, 8)
        add_cylinder(bm, (0, 0, h - 0.02), 0.15 + 0.03 * (k == 1), 0.04, 10, 2)
        add_cylinder(bm, (0, 0, h + 0.05), 0.09, 0.12, 10, 2)
        o = object_from_bmesh(f"PROTO_PASSANT_{k}", bm, coll,
                              location=(0, 0, -100))
        for m in (M["personne"], M["chair"], M["chapeau"]):
            o.data.materials.append(m)
        protos.append(o)
    for i in range(count):
        (u0, u1, v0, v1) = rnd.choice(zones)
        instance(rnd.choice(protos), f"PASSANT_{i:03d}", coll,
                 (rnd.uniform(u0, u1), rnd.uniform(v0, v1), 0.15),
                 rnd.uniform(0, math.tau))
