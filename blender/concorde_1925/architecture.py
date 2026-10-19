"""Palais de Gabriel (Hôtel de la Marine, Automobile Club / Hôtel de Crillon)
et chambre du 2e étage du Crillon.

Composition de chaque palais, de bas en haut : rez-de-chaussée à arcades en
plein cintre (soubassement), colonnade corinthienne de douze colonnes devant
une galerie (loggia) qui couvre le 1er étage (étage noble) et le 2e étage,
entablement, balustrade, toiture d'ardoise. Deux avant-corps à fronton
encadrent la colonnade.
"""
from __future__ import annotations

import math

import bmesh

import geo
from helpers import (add_box, add_cylinder, add_prism, add_sphere,
                     add_wall_with_openings, add_wall_xz, arch_spandrel,
                     object_from_bmesh)

F = geo.GABRIEL_FACADE_V
WALL_V0 = F + geo.GABRIEL_LOGGIA_DEPTH        # mur des fenêtres, derrière la loggia
WALL_T = 0.7
PAVILION_W = 22.0
N_COLUMNS = 12

# Chambre du Crillon (2e étage, 3e travée de la colonnade en partant de l'ouest)
ROOM_BAY = 2
ROOM_DEPTH = 7.5
ROOM_WIDTH = 6.4
ROOM_HEIGHT = 4.1
WIN2_W, WIN2_Z0, WIN2_Z1 = 1.7, geo.GABRIEL_FLOOR_2 + 0.35, geo.GABRIEL_FLOOR_2 + 2.75
WIN1_W, WIN1_Z0, WIN1_Z1 = 2.0, geo.GABRIEL_FLOOR_1 + 0.3, geo.GABRIEL_FLOOR_1 + 4.6


def _layout(u0: float, u1: float):
    col_u0, col_u1 = u0 + PAVILION_W, u1 - PAVILION_W
    step = (col_u1 - col_u0) / N_COLUMNS
    columns = [col_u0 + step * (k + 0.5) for k in range(N_COLUMNS)]
    bays = [(columns[k] + columns[k + 1]) / 2 for k in range(N_COLUMNS - 1)]
    pav_bays = []
    for pu0 in (u0, u1 - PAVILION_W):
        cols = [pu0 + 3.0 + i * (PAVILION_W - 6.0) / 3 for i in range(4)]
        pav_bays.append((cols, [(cols[i] + cols[i + 1]) / 2 for i in range(3)]))
    return col_u0, col_u1, columns, bays, pav_bays


def _column(bm, u, v, z0, z1, r, mat_index, engaged=False):
    add_box(bm, (u, v, z0 + 0.25), (2.6 * r, 2.6 * r, 0.5), mat_index)
    add_cylinder(bm, (u, v, z0 + 0.62), 1.2 * r, 0.25, 16, mat_index)
    shaft = z1 - z0 - 1.9
    add_cylinder(bm, (u, v, z0 + 0.75 + shaft / 2), r, shaft, 20, mat_index,
                 radius_top=r * 0.86)
    # chapiteau corinthien : corbeille évasée + abaque
    add_cylinder(bm, (u, v, z1 - 0.65), r * 0.9, 0.9, 16, mat_index,
                 radius_top=r * 1.35)
    add_box(bm, (u, v, z1 - 0.1), (2.9 * r, 2.9 * r, 0.2), mat_index)


def _balustrade(bm, u0, u1, v, z, height, mat_index, depth=0.6):
    add_box(bm, ((u0 + u1) / 2, v, z + 0.12), (u1 - u0, depth, 0.24), mat_index)
    add_box(bm, ((u0 + u1) / 2, v, z + height - 0.1), (u1 - u0, depth + 0.1,
                                                       0.2), mat_index)
    n = max(1, int((u1 - u0) / 0.34))
    for i in range(n):
        u = u0 + (i + 0.5) * (u1 - u0) / n
        add_cylinder(bm, (u, v, z + height / 2), 0.11, height - 0.44, 6,
                     mat_index, radius_top=0.08)


def gabriel_palace(coll, M, name: str, u0: float, u1: float,
                   room_bay: int | None = None):
    """Construit un palais ; renvoie la position de la fenêtre de la chambre."""
    col_u0, col_u1, columns, bays, pav_bays = _layout(u0, u1)
    depth = geo.GABRIEL_DEPTH
    zA, z1, z2 = geo.GABRIEL_ARCADE_TOP, geo.GABRIEL_FLOOR_1, geo.GABRIEL_FLOOR_2
    zC, zE, zB = (geo.GABRIEL_COLUMN_TOP, geo.GABRIEL_CORNICE_TOP,
                  geo.GABRIEL_BALUSTRADE_TOP)
    bm = bmesh.new()  # 0 pierre, 1 vitre, 2 ardoise, 3 fonte
    # --- Rez-de-chaussée à arcades -----------------------------------------
    arches = [(b, 2.9) for b in bays]
    for cols, pbays in pav_bays:
        arches += [(b, 2.6) for b in pbays]
    arches.sort()
    edges = [u0] + [(a[0] + b[0]) / 2 for a, b in zip(arches, arches[1:])] + [u1]
    z_spring = 4.9
    for (uc, w), ea, eb in zip(arches, edges, edges[1:]):
        xa, xb = uc - w / 2, uc + w / 2
        add_box(bm, ((ea + xa) / 2, F + 0.2, z_spring / 2),
                (xa - ea, 1.0, z_spring), 0)
        add_box(bm, ((xb + eb) / 2, F + 0.2, z_spring / 2),
                (eb - xb, 1.0, z_spring), 0)
        add_wall_xz(bm, arch_spandrel(ea, eb, xa, xb, z_spring, zA),
                    F - 0.3, F + 0.7, 0)
        # vitrine / porte au fond de la galerie
        add_box(bm, (uc, F + 2.15, 2.9), (w - 0.3, 0.1, 5.4), 1)
    add_box(bm, ((u0 + u1) / 2, F - 0.35, zA - 0.25), (u1 - u0, 0.5, 0.5), 0)
    add_box(bm, ((u0 + u1) / 2, F + 1.5 + depth / 2, zA / 2),
            (u1 - u0, depth - 1.5, zA), 0)
    # --- Terrasse de la loggia et colonnade ----------------------------------
    add_box(bm, ((col_u0 + col_u1) / 2, (F - 0.3 + WALL_V0) / 2, (zA + z1) / 2),
            (col_u1 - col_u0, WALL_V0 - F + 0.3, z1 - zA), 0)
    for u in columns:
        _column(bm, u, F + 0.6, z1, zC, 0.56, 0)
    for k in range(N_COLUMNS - 1):
        _balustrade(bm, columns[k] + 0.8, columns[k + 1] - 0.8, F + 0.6, z1,
                    1.05, 0, 0.45)
    # mur des fenêtres de la loggia (1er et 2e étages)
    openings = []
    for i, b in enumerate(bays):
        openings.append((b - WIN1_W / 2, b + WIN1_W / 2, WIN1_Z0, WIN1_Z1))
        openings.append((b - WIN2_W / 2, b + WIN2_W / 2, WIN2_Z0, WIN2_Z1))
    add_wall_with_openings(bm, col_u0, col_u1, WALL_V0, WALL_V0 + WALL_T,
                           z1, zE, openings, 0)
    for i, b in enumerate(bays):
        add_box(bm, (b, WALL_V0 + 0.3, (WIN1_Z0 + WIN1_Z1) / 2),
                (WIN1_W, 0.06, WIN1_Z1 - WIN1_Z0), 1)
        if i != room_bay:
            add_box(bm, (b, WALL_V0 + 0.3, (WIN2_Z0 + WIN2_Z1) / 2),
                    (WIN2_W, 0.06, WIN2_Z1 - WIN2_Z0), 1)
        # chambranles
        add_box(bm, (b, WALL_V0 - 0.08, WIN1_Z1 + 0.25), (WIN1_W + 0.6, 0.2,
                                                          0.5), 0)
        add_box(bm, (b, WALL_V0 - 0.05, WIN1_Z0 - 0.1), (WIN1_W + 0.3, 0.15,
                                                         0.2), 0)
    # plafond de la loggia + entablement
    add_box(bm, ((col_u0 + col_u1) / 2, (F + WALL_V0) / 2, (zC + zE) / 2),
            (col_u1 - col_u0, WALL_V0 - F + 0.2, zE - zC), 0)
    # --- Avant-corps à fronton -------------------------------------------------
    for cols, pbays in pav_bays:
        pu0, pu1 = cols[0] - 3.0, cols[-1] + 3.0
        pops = []
        for b in pbays:
            pops.append((b - WIN1_W / 2, b + WIN1_W / 2, WIN1_Z0, WIN1_Z1))
            pops.append((b - WIN2_W / 2, b + WIN2_W / 2, WIN2_Z0, WIN2_Z1))
            add_box(bm, (b, F + 0.4, (WIN1_Z0 + WIN1_Z1) / 2),
                    (WIN1_W, 0.06, WIN1_Z1 - WIN1_Z0), 1)
            add_box(bm, (b, F + 0.4, (WIN2_Z0 + WIN2_Z1) / 2),
                    (WIN2_W, 0.06, WIN2_Z1 - WIN2_Z0), 1)
            _balustrade(bm, b - 1.2, b + 1.2, F - 0.25, z1 - 0.1, 1.0, 0, 0.4)
        add_wall_with_openings(bm, pu0, pu1, F - 0.2, F + 0.6, zA, zE, pops, 0)
        add_box(bm, ((pu0 + pu1) / 2, F + 0.6 + depth / 2, (zA + zE) / 2),
                (pu1 - pu0, depth - 0.6, zE - zA), 0)
        for u in cols:
            _column(bm, u, F - 0.45, z1, zC, 0.56, 0)
        add_box(bm, ((pu0 + pu1) / 2, F - 0.4, (zC + zE) / 2),
                (pu1 - pu0, 1.2, zE - zC), 0)
        # fronton triangulaire
        add_wall_xz(bm, [(pu0 - 0.3, zE), (pu1 + 0.3, zE),
                         ((pu0 + pu1) / 2, zE + 4.2)], F - 1.0, F + 1.5, 0)
        add_box(bm, ((pu0 + pu1) / 2, F - 0.7, zE + 1.0), (8.0, 0.4, 1.6), 0)
    # --- Corps de bâtiment derrière la loggia (laisse la place de la chambre)
    core_v0 = WALL_V0 + WALL_T + (ROOM_DEPTH + 0.4 if room_bay is not None
                                  else 0.0)
    add_box(bm, ((col_u0 + col_u1) / 2, (core_v0 + F + depth) / 2,
                 (zA + zE) / 2), (col_u1 - col_u0, F + depth - core_v0,
                                  zE - zA), 0)
    if room_bay is not None:
        # le reste de l'étage autour de la chambre est fermé par des refends
        add_box(bm, ((col_u0 + col_u1) / 2, (WALL_V0 + WALL_T + core_v0) / 2,
                     (zA + z2) / 2), (col_u1 - col_u0, core_v0 - WALL_V0 - WALL_T,
                                      z2 - zA), 0)
        add_box(bm, ((col_u0 + col_u1) / 2, (WALL_V0 + WALL_T + core_v0) / 2,
                     (z2 + ROOM_HEIGHT + 0.3 + zE) / 2),
                (col_u1 - col_u0, core_v0 - WALL_V0 - WALL_T,
                 zE - z2 - ROOM_HEIGHT - 0.3), 0)
        rb = bays[room_bay]
        for side in (-1, 1):
            a = rb + side * (ROOM_WIDTH / 2 + 0.3)
            b = col_u0 if side < 0 else col_u1
            add_box(bm, ((a + b) / 2, (WALL_V0 + WALL_T + core_v0) / 2,
                         z2 + (ROOM_HEIGHT + 0.3) / 2),
                    (abs(b - a), core_v0 - WALL_V0 - WALL_T, ROOM_HEIGHT + 0.3),
                    0)
    # --- Balustrade sommitale et toiture -------------------------------------
    add_box(bm, ((u0 + u1) / 2, F - 0.1, zE - 0.2), (u1 - u0 + 0.4, 1.8, 0.4),
            0)
    _balustrade(bm, col_u0, col_u1, F + 0.2, zE, zB - zE, 0, 0.55)
    roof = [(u0 + 0.5, F + 1.2), (u1 - 0.5, F + 1.2),
            (u1 - 0.5, F + depth - 0.5), (u0 + 0.5, F + depth - 0.5)]
    roof_top = [(u0 + 4.5, F + 5.5), (u1 - 4.5, F + 5.5),
                (u1 - 4.5, F + depth - 4.5), (u0 + 4.5, F + depth - 4.5)]
    add_prism(bm, roof, zE, zE + 6.5, 2, top_outline=roof_top)
    for k in range(6):
        u = u0 + 8 + k * (u1 - u0 - 16) / 5
        add_box(bm, (u, F + 12, zE + 7.0), (1.4, 0.7, 3.0), 0)
        add_box(bm, (u, F + 3.4, zE + 1.6), (1.4, 1.0, 1.8), 2)  # lucarnes
    obj = object_from_bmesh(name, bm, coll)
    for m in (M["pierre"], M["vitre"], M["ardoise"], M["fonte"]):
        obj.data.materials.append(m)
    if room_bay is None:
        return None
    return {"u": bays[room_bay], "v": WALL_V0, "columns": columns}


def crillon_room(coll, M, window_u: float):
    """Chambre Louis XVI du 2e étage, fenêtre ouverte sur la place.

    Renvoie (position œil, cible) dans le repère place pour la caméra.
    """
    v0 = WALL_V0 + WALL_T
    v1 = v0 + ROOM_DEPTH
    zf = geo.GABRIEL_FLOOR_2
    zc = zf + ROOM_HEIGHT
    ua, ub = window_u - ROOM_WIDTH / 2, window_u + ROOM_WIDTH / 2
    uc = window_u
    bm = bmesh.new()
    # 0 parquet, 1 boiserie, 2 moulure dorée, 3 velours, 4 voilage, 5 tapis,
    # 6 tissu, 7 marbre, 8 vitre, 9 bois (châssis)
    add_box(bm, (uc, (v0 + v1) / 2, zf - 0.1), (ROOM_WIDTH, ROOM_DEPTH, 0.2), 0)
    add_box(bm, (uc, (v0 + v1) / 2, zc + 0.1), (ROOM_WIDTH, ROOM_DEPTH, 0.2), 1)
    add_box(bm, (ua - 0.1, (v0 + v1) / 2, (zf + zc) / 2),
            (0.2, ROOM_DEPTH, ROOM_HEIGHT), 1)
    add_box(bm, (ub + 0.1, (v0 + v1) / 2, (zf + zc) / 2),
            (0.2, ROOM_DEPTH, ROOM_HEIGHT), 1)
    add_box(bm, (uc, v1 + 0.1, (zf + zc) / 2), (ROOM_WIDTH + 0.4, 0.2,
                                                 ROOM_HEIGHT), 1)
    # face intérieure du mur de façade autour de la fenêtre
    add_wall_with_openings(bm, ua, ub, v0, v0 + 0.05, zf, zc,
                           [(uc - WIN2_W / 2, uc + WIN2_W / 2, WIN2_Z0,
                             WIN2_Z1)], 1)
    # corniche et cadres dorés des boiseries
    for u, w in ((ua + 0.06, None), (ub - 0.06, None)):
        add_box(bm, (u, (v0 + v1) / 2, zc - 0.15), (0.12, ROOM_DEPTH, 0.3), 1)
    add_box(bm, (uc, v1 - 0.06, zc - 0.15), (ROOM_WIDTH, 0.12, 0.3), 1)
    add_box(bm, (uc, v0 + 0.11, zc - 0.15), (ROOM_WIDTH, 0.12, 0.3), 1)
    for side in (ua + 0.03, ub - 0.03):
        for k in range(3):
            vv = v0 + 1.2 + k * 2.2
            for dz, h in ((0.35, 0.03), (2.9, 0.03)):
                add_box(bm, (side, vv, zf + dz), (0.02, 1.6, h), 2)
            for dv in (-0.8, 0.8):
                add_box(bm, (side, vv + dv, zf + 1.62), (0.02, 0.03, 2.55), 2)
        add_box(bm, (side, (v0 + v1) / 2, zf + 0.12), (0.05, ROOM_DEPTH, 0.24),
                1)  # plinthe
    # embrasure : ébrasements et appui
    for s in (-1, 1):
        add_box(bm, (uc + s * (WIN2_W / 2 + 0.01), WALL_V0 + WALL_T / 2,
                     (WIN2_Z0 + WIN2_Z1) / 2), (0.02, WALL_T, WIN2_Z1 - WIN2_Z0),
                1)
    add_box(bm, (uc, WALL_V0 + WALL_T / 2 + 0.05, WIN2_Z0 - 0.02),
            (WIN2_W + 0.1, WALL_T + 0.1, 0.06), 7)
    # croisée à deux vantaux ouverts vers l'intérieur, petits-bois
    leaf_w = WIN2_W / 2
    hz = WIN2_Z1 - WIN2_Z0
    for s in (-1, 1):
        hinge_u = uc + s * leaf_w
        du, dv = -s * math.cos(math.radians(78)), math.sin(math.radians(78))
        cu = hinge_u + du * leaf_w / 2
        cv = v0 + dv * leaf_w / 2
        rot = math.atan2(dv, du)
        add_box(bm, (cu, cv, WIN2_Z0 + hz / 2), (leaf_w, 0.05, 0.07), 9, rot)
        for zz in (0.04, hz / 3, 2 * hz / 3, hz - 0.04):
            add_box(bm, (cu, cv, WIN2_Z0 + zz), (leaf_w, 0.05, 0.06), 9, rot)
        for f in (0.03, 0.97):
            add_box(bm, (hinge_u + du * leaf_w * f, v0 + dv * leaf_w * f,
                         WIN2_Z0 + hz / 2), (0.06, 0.05, hz), 9, rot)
        add_box(bm, (cu, cv, WIN2_Z0 + hz / 2), (leaf_w - 0.08, 0.01, hz - 0.08),
                8, rot)
    # rideaux de velours retenus par des embrasses + voilages
    for s in (-1, 1):
        u = uc + s * (WIN2_W / 2 + 0.4)
        for k in range(9):  # plis du velours, resserrés par l'embrasse
            off = (k - 4) * 0.075
            add_cylinder(bm, (u + s * off * 1.4, v0 + 0.22 + 0.04 * (k % 2),
                              zf + 2.6), 0.055, 2.8, 8, 3)
            add_cylinder(bm, (u + s * off, v0 + 0.22 + 0.04 * (k % 2),
                              zf + 0.6), 0.055, 1.2, 8, 3, radius_top=0.05)
        add_cylinder(bm, (u, v0 + 0.24, zf + 1.2), 0.42, 0.06, 16, 2)
        add_box(bm, (uc + s * (WIN2_W / 2 - 0.15), v0 + 0.12, zf + 1.9),
                (0.35, 0.02, 3.6), 4)
    add_box(bm, (uc, v0 + 0.25, zc - 0.25), (WIN2_W + 1.8, 0.35, 0.3), 2)
    # tapis, deux bergères, guéridon et vase de fleurs
    add_box(bm, (uc, v0 + 3.0, zf + 0.01), (3.6, 4.0, 0.02), 5)
    for s in (-1, 1):
        u, v = uc + s * 1.35, v0 + 1.6
        add_box(bm, (u, v, zf + 0.42), (0.75, 0.7, 0.14), 6)
        add_sphere(bm, (u, v + 0.33, zf + 0.82), 0.4, 6, 12, (0.95, 0.18, 0.95))
        add_box(bm, (u, v + 0.02, zf + 0.53), (0.68, 0.62, 0.1), 6)  # coussin
        for a in (-1, 1):
            add_box(bm, (u + a * 0.36, v, zf + 0.6), (0.06, 0.65, 0.12), 9)
            for b in (-1, 1):
                add_cylinder(bm, (u + a * 0.32, v + b * 0.28, zf + 0.17), 0.03,
                             0.35, 6, 9, radius_top=0.025)
    gu, gv = uc - 1.25, v0 + 3.0
    add_cylinder(bm, (gu, gv, zf + 0.72), 0.38, 0.04, 24, 7)
    add_cylinder(bm, (gu, gv, zf + 0.36), 0.04, 0.7, 8, 9)
    add_cylinder(bm, (gu, gv, zf + 0.85), 0.06, 0.22, 10, 7, radius_top=0.04)
    for k in range(7):  # bouquet
        a = k * math.tau / 7
        add_sphere(bm, (gu + 0.08 * math.cos(a), gv + 0.08 * math.sin(a),
                        zf + 1.02 + 0.04 * (k % 3)), 0.05, 3, 6)
    # cheminée de marbre et trumeau (miroir) sur le mur ouest
    add_box(bm, (ua + 0.2, v0 + 4.2, zf + 0.55), (0.4, 1.6, 1.1), 7)
    add_box(bm, (ua + 0.25, v0 + 4.2, zf + 1.12), (0.5, 1.8, 0.06), 7)
    add_box(bm, (ua + 0.04, v0 + 4.2, zf + 2.3), (0.04, 1.4, 1.9), 8)
    add_box(bm, (ua + 0.05, v0 + 4.2, zf + 2.3), (0.05, 1.55, 2.05), 2)
    # lustre éteint
    add_cylinder(bm, (uc, v0 + 3.5, zc - 0.4), 0.01, 0.8, 4, 2)
    add_cylinder(bm, (uc, v0 + 3.5, zc - 0.9), 0.45, 0.35, 12, 2,
                 radius_top=0.2)
    obj = object_from_bmesh("CHAMBRE_CRILLON_2E_ETAGE", bm, coll)
    for m in (M["parquet"], M["boiserie"], M["moulure_or"], M["velours"],
              M["voilage"], M["tapis"], M["tissu"], M["marbre"], M["vitre"],
              M["boiserie"]):
        obj.data.materials.append(m)
    eye = (uc + 0.9, v0 + 4.6, zf + 1.45)
    target = (0.0, 0.0, 6.0)  # l'obélisque
    return eye, target
