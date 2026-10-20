"""Véhicules parisiens de 1925, modélisés de façon procédurale.

Modèles (silhouettes fidèles aux proportions, détails simplifiés) :
  - Citroën 5 HP « Trèfle » / Type C (1922-1926), torpédo ;
  - Citroën B12 conduite intérieure (1925) ;
  - taxi Renault KZ de la Compagnie G7, landaulet ;
  - Renault NN torpédo (1924) ;
  - Ford T conduite intérieure (montée à Bordeaux / Asnières) ;
  - Hispano-Suiza H6B torpédo, voiture de maître ;
  - camionnette de livraison (Citroën B2 fourgonnette) ;
  - autobus Schneider H de la STCRP (vert et crème, plate-forme arrière) ;
  - fiacre attelé (encore quelques-uns en 1925).

Chaque modèle est construit une fois (prototype masqué) ; les voitures de la
scène en sont des copies liées : la peinture est un emplacement de matériau
« lié à l'objet », donc chaque voiture a sa couleur. Les roues sont des objets
séparés qui tournent grâce à un pilote (driver) sans Python.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import bmesh
import bpy

import geo
from helpers import add_box, add_cylinder, add_sphere, collection, link
from materials import car_paint

# index des matériaux dans le maillage d'une carrosserie
PAINT, BLACK, NICKEL, LEATHER, GLASS, LAMP, ACCENT = range(7)


@dataclass
class CarSpec:
    key: str
    label: str
    length: float
    width: float
    wheelbase: float
    wheel_r: float
    hood_len: float
    hood_h: float
    body: str            # torpedo | berline | landaulet | fourgon
    roof_h: float = 1.0
    paints: tuple = ("noir",)
    accent: str | None = None
    speed: float = 8.0   # m/s (≈ 30 km/h)


CARS = [
    CarSpec("citroen_5hp", "Citroën 5 HP Trèfle", 3.2, 1.40, 2.25, 0.33, 0.85,
            0.62, "torpedo", paints=("jaune_citron", "bleu_nuit", "vert_bouteille",
                                     "noir"), speed=7.0),
    CarSpec("citroen_b12", "Citroën B12 conduite intérieure", 4.0, 1.60, 2.83,
            0.38, 1.10, 0.72, "berline", 1.05,
            paints=("noir", "bleu_nuit", "bordeaux", "gris_taupe")),
    CarSpec("taxi_g7", "Taxi Renault KZ G7", 3.9, 1.55, 2.80, 0.38, 1.05, 0.78,
            "landaulet", 1.0, paints=("rouge_taxi",), accent="noir", speed=9.0),
    CarSpec("renault_nn", "Renault NN torpédo", 3.6, 1.50, 2.65, 0.36, 1.0, 0.72,
            "torpedo", paints=("vert_bouteille", "noir", "gris_taupe")),
    CarSpec("ford_t", "Ford T conduite intérieure", 3.7, 1.65, 2.54, 0.38, 0.95,
            0.72, "berline", 1.2, paints=("noir",)),
    CarSpec("hispano_h6", "Hispano-Suiza H6B", 4.9, 1.75, 3.40, 0.45, 1.75,
            0.82, "torpedo", paints=("creme", "bordeaux", "bleu_nuit"),
            accent="noir", speed=10.0),
    CarSpec("fourgonnette", "Citroën B2 fourgonnette", 3.9, 1.55, 2.83, 0.38,
            1.05, 0.72, "fourgon", 1.25, paints=("vert_bouteille", "gris_taupe",
                                                 "bordeaux")),
]


def _torus_y(bm, center, R, r, mat, seg=20, ring=8):
    """Pneu : tore d'axe Y."""
    cx, cy, cz = center
    rows = []
    for i in range(seg):
        a = i * math.tau / seg
        row = []
        for j in range(ring):
            b = j * math.tau / ring
            rr = R + r * math.cos(b)
            row.append(bm.verts.new((cx + rr * math.cos(a), cy + r * math.sin(b),
                                     cz + rr * math.sin(a))))
        rows.append(row)
    for i in range(seg):
        for j in range(ring):
            f = bm.faces.new((rows[i][j], rows[(i + 1) % seg][j],
                              rows[(i + 1) % seg][(j + 1) % ring],
                              rows[i][(j + 1) % ring]))
            f.material_index = mat


def _wheel_mesh(name, r, spokes=10, wood=True, M=None):
    bm = bmesh.new()  # 0 pneu, 1 bois/peinture, 2 nickel
    _torus_y(bm, (0, 0, 0), r - 0.055, 0.058, 0)
    add_cylinder(bm, (0, 0, 0), r - 0.1, 0.07, 24, 1, axis="Y", caps=False)
    add_cylinder(bm, (0, 0, 0), r - 0.13, 0.07, 24, 1, axis="Y", caps=False)
    for k in range(spokes):
        a = k * math.tau / spokes
        rr = (r - 0.12) / 2
        # rayon orienté radialement
        add_box(bm, (rr * math.cos(a), 0, rr * math.sin(a)),
                (0.045, 0.05, r - 0.1), 1, rot_y=math.pi / 2 - a)
    add_cylinder(bm, (0, 0, 0), r * 0.17, 0.16, 12, 2, axis="Y")
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in (M["pneu"], M["bois_roue"] if wood else M["fonte"], M["nickel"]):
        me.materials.append(m)
    return me


def _fender(bm, x, y, r, width, start_deg, end_deg, mat):
    seg = 9
    R = r + 0.09
    for k in range(seg):
        a0 = math.radians(start_deg + (end_deg - start_deg) * k / seg)
        a1 = math.radians(start_deg + (end_deg - start_deg) * (k + 1) / seg)
        am = (a0 + a1) / 2
        L = R * abs(a1 - a0) + 0.02
        cx, cz = x + R * math.cos(am), r + R * math.sin(am)
        add_box(bm, (cx, y, cz), (L, width, 0.035), mat,
                rot_y=-(am + math.pi / 2))


def build_car_body(spec: CarSpec, M):
    L, W, wb, r = spec.length, spec.width, spec.wheelbase, spec.wheel_r
    T = W - 0.25
    bw = W - 0.55
    xf, xr = wb / 2, -wb / 2
    bm = bmesh.new()
    zc = r + 0.02                                   # haut du châssis
    add_box(bm, ((xf + 0.3 + xr - 0.5) / 2, 0, zc), (wb + 0.8, bw - 0.1, 0.16),
            BLACK)
    # radiateur, capot, tablier
    x_rad = xf + 0.08
    hh = spec.hood_h
    add_box(bm, (x_rad, 0, zc + hh / 2), (0.12, bw * 0.72, hh), NICKEL)
    add_box(bm, (x_rad + 0.065, 0, zc + hh / 2), (0.01, bw * 0.6, hh * 0.85),
            BLACK)
    add_cylinder(bm, (x_rad, 0, zc + hh + 0.06), 0.04, 0.12, 8, NICKEL)
    x_cowl = x_rad - spec.hood_len
    add_box(bm, ((x_rad + x_cowl) / 2, 0, zc + hh / 2 - 0.02),
            (x_rad - x_cowl - 0.05, bw * 0.7, hh - 0.04), PAINT)
    add_cylinder(bm, ((x_rad + x_cowl) / 2, 0, zc + hh - 0.06),
                 bw * 0.35, x_rad - x_cowl - 0.05, 12, PAINT, axis="X")
    # garde-boue et marchepieds
    for s in (-1, 1):
        y = s * T / 2
        _fender(bm, xf, y, r, 0.27, 15, 150, BLACK)
        _fender(bm, xr, y, r, 0.27, 30, 168, BLACK)
        rb_y = s * (bw / 2 + 0.14)
        add_box(bm, ((xf - r - 0.05 + xr + r + 0.05) / 2, rb_y, r * 0.72),
                (wb - 2 * r - 0.1, 0.26, 0.04), BLACK)
        # raccord aile avant → marchepied
        add_box(bm, (xf - r - 0.1, y, r * 0.95), (0.35, 0.27, 0.035), BLACK)
    # phares sur barre, lanternes
    for s in (-1, 1):
        add_cylinder(bm, (x_rad + 0.12, s * W * 0.3, zc + hh * 0.72), 0.12, 0.17,
                     12, BLACK, axis="X")
        add_cylinder(bm, (x_rad + 0.21, s * W * 0.3, zc + hh * 0.72), 0.1, 0.02,
                     12, LAMP, axis="X")
        add_cylinder(bm, (x_cowl + 0.05, s * (bw / 2 + 0.02), zc + hh + 0.05),
                     0.05, 0.1, 8, NICKEL, axis="X")
    add_box(bm, (x_rad + 0.1, 0, zc + hh * 0.72), (0.04, W * 0.6, 0.03), NICKEL)
    # caisse
    x_back = -L / 2 + 0.25
    belt = zc + hh + 0.08
    add_box(bm, (x_cowl - 0.15, 0, zc + (hh + 0.1) / 2), (0.3, bw, hh + 0.1),
            PAINT)
    if spec.body in ("torpedo", "landaulet"):
        x_ws = x_cowl - 0.3
        # pare-brise
        add_box(bm, (x_ws, 0, belt + 0.28), (0.015, bw - 0.1, 0.52), GLASS)
        for s in (-1, 1):
            add_cylinder(bm, (x_ws, s * (bw / 2 - 0.04), belt + 0.28), 0.015,
                         0.58, 6, NICKEL)
        # baquet ouvert : parois, sièges, volant
        x_mid = (x_ws + x_back) / 2
        if spec.body == "torpedo":
            for s in (-1, 1):
                add_box(bm, (x_mid, s * (bw / 2 - 0.03), (zc + belt) / 2),
                        (x_ws - x_back, 0.06, belt - zc), PAINT)
            add_box(bm, (x_back + 0.05, 0, (zc + belt) / 2), (0.1, bw, belt - zc),
                    PAINT)
            add_box(bm, (x_mid, 0, zc + 0.12), (x_ws - x_back, bw - 0.1, 0.1),
                    BLACK)
            for xs in (x_ws - 0.75, x_back + 0.55):
                add_box(bm, (xs, 0, zc + 0.35), (0.5, bw - 0.15, 0.2), LEATHER)
                add_box(bm, (xs - 0.25, 0, zc + 0.62), (0.1, bw - 0.15, 0.55),
                            LEATHER)
            # capote repliée
            add_cylinder(bm, (x_back + 0.15, 0, belt + 0.12), 0.16, bw - 0.05,
                         10, BLACK, axis="Y")
        else:  # landaulet : chauffeur à découvert, compartiment arrière fermé
            x_div = x_ws - 0.8
            for s in (-1, 1):
                add_box(bm, ((x_ws + x_div) / 2, s * (bw / 2 - 0.03),
                             (zc + belt) / 2), (x_ws - x_div, 0.06, belt - zc),
                        ACCENT)
            add_box(bm, (x_ws - 0.45, 0, zc + 0.35), (0.45, bw - 0.15, 0.2),
                    LEATHER)
            top = belt + spec.roof_h * 0.9
            add_box(bm, ((x_div + x_back) / 2, 0, (zc + belt) / 2),
                    (x_div - x_back, bw, belt - zc), PAINT)
            add_box(bm, ((x_div + x_back) / 2 + 0.05, 0, (belt + top) / 2),
                    (x_div - x_back - 0.1, bw - 0.06, top - belt), GLASS)
            for xp in (x_div, x_div - 0.55, x_back + 0.05):
                add_box(bm, (xp, 0, (belt + top) / 2), (0.08, bw, top - belt),
                        ACCENT)
            add_box(bm, ((x_div + x_back) / 2, 0, top + 0.04),
                    (x_div - x_back + 0.08, bw + 0.04, 0.1), BLACK)
            add_cylinder(bm, (x_back + 0.35, 0, top - 0.1), 0.3, bw + 0.02, 10,
                         BLACK, axis="Y")
            # compteur horokilométrique
            add_box(bm, (x_ws + 0.05, bw / 2 - 0.1, belt + 0.1), (0.1, 0.12, 0.15),
                    NICKEL)
        add_cylinder(bm, (x_ws - 0.4, bw / 4, belt + 0.12), 0.19, 0.03, 16, BLACK,
                     axis="X")
    else:  # berline / fourgon : caisse fermée
        x_ws = x_cowl - 0.25
        top = belt + spec.roof_h
        add_box(bm, ((x_ws + x_back) / 2, 0, (zc + belt) / 2),
                (x_ws - x_back, bw, belt - zc), PAINT)
        if spec.body == "berline":
            add_box(bm, ((x_ws + x_back) / 2, 0, (belt + top) / 2),
                    (x_ws - x_back - 0.06, bw - 0.06, top - belt), GLASS)
            n_pill = 3
            for k in range(n_pill + 1):
                xp = x_ws - k * (x_ws - x_back) / n_pill
                add_box(bm, (xp, 0, (belt + top) / 2), (0.09, bw, top - belt),
                        PAINT)
            add_box(bm, ((x_ws + x_back) / 2, 0, top + 0.05),
                    (x_ws - x_back + 0.12, bw + 0.06, 0.1), BLACK)
            add_box(bm, (x_back - 0.25, 0, belt - 0.1), (0.45, bw - 0.1, 0.5),
                    BLACK)  # malle
        else:
            x_cab = x_ws - 0.85
            add_box(bm, ((x_ws + x_cab) / 2, 0, (belt + top) / 2),
                    (x_ws - x_cab - 0.06, bw - 0.06, top - belt), GLASS)
            for xp in (x_ws, x_cab):
                add_box(bm, (xp, 0, (belt + top) / 2), (0.09, bw, top - belt),
                        PAINT)
            add_box(bm, ((x_cab + x_back) / 2 - 0.1, 0, (zc + top + 0.15) / 2),
                    (x_cab - x_back + 0.2, bw + 0.2, top + 0.15 - zc), PAINT)
            add_box(bm, ((x_ws + x_back) / 2, 0, top + 0.12),
                    (x_ws - x_back + 0.25, bw + 0.24, 0.06), BLACK)
    # roue de secours à l'arrière
    add_cylinder(bm, (x_back - 0.12, 0, zc + r), r, 0.12, 16, BLACK, axis="X")
    obj = bpy.data.objects.new(f"PROTO_{spec.key.upper()}",
                               _finish(bm, f"CARROSSERIE_{spec.key}"))
    _materials(obj, M, spec)
    wheels = [(xf, T / 2), (xf, -T / 2), (xr, T / 2), (xr, -T / 2)]
    return obj, wheels


def _finish(bm, name):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    return me


def _materials(obj, M, spec_paint, accent=None):
    me = obj.data
    paint = car_paint(spec_paint.paints[0]) if hasattr(spec_paint, "paints") \
        else spec_paint
    acc = getattr(spec_paint, "accent", None) or accent
    for m in (paint, M["capote"], M["nickel"], M["cuir"], M["vitre"],
              M["phare"], car_paint(acc) if acc else paint):
        me.materials.append(m)


def build_bus(M):
    """Autobus Schneider H (STCRP), 1916-1937 : 8,3 m, plate-forme arrière."""
    L, W, wb, r = 8.3, 2.3, 4.7, 0.48
    bm = bmesh.new()
    xf, xr = 2.6, -2.1
    zc = r + 0.05
    add_box(bm, (0.2, 0, zc), (7.2, W - 0.5, 0.2), BLACK)
    add_box(bm, (xf + 0.75, 0, zc + 0.55), (1.4, 0.95, 1.0), PAINT)    # capot
    add_box(bm, (xf + 1.48, 0, zc + 0.55), (0.1, 0.9, 1.0), NICKEL)
    for s in (-1, 1):
        add_cylinder(bm, (xf + 1.55, s * 0.6, zc + 0.85), 0.13, 0.15, 10, LAMP,
                     axis="X")
        _fender(bm, xf, s * (W / 2 - 0.25), r, 0.3, 170, 20, BLACK)
    # poste de conduite ouvert sur les côtés, caisse voyageurs
    add_box(bm, (xf - 0.3, 0, zc + 1.35), (1.0, W, 0.06), BLACK)
    add_box(bm, (xf + 0.05, 0, zc + 0.95), (0.03, W - 0.3, 0.8), GLASS)
    xb0, xb1 = xf - 0.6, xr - 1.1
    add_box(bm, ((xb0 + xb1) / 2, 0, zc + 0.6), (xb0 - xb1, W, 1.0), PAINT)
    add_box(bm, ((xb0 + xb1) / 2, 0, zc + 1.55), (xb0 - xb1 - 0.05, W - 0.04, 0.9),
            GLASS)
    for k in range(7):
        xp = xb0 - k * (xb0 - xb1) / 6
        add_box(bm, (xp, 0, zc + 1.55), (0.1, W, 0.9), ACCENT)
    add_box(bm, ((xb0 + xb1) / 2, 0, zc + 2.15), (xb0 - xb1 + 0.1, W + 0.04, 0.3),
            ACCENT)
    add_box(bm, ((xb0 + xb1) / 2, 0, zc + 2.36), (xb0 - xb1 + 0.3, W + 0.1, 0.12),
            BLACK)
    add_box(bm, (xb0 - 0.3, 0, zc + 2.55), (0.9, 1.3, 0.3), ACCENT)    # girouette
    # plate-forme arrière ouverte avec rambarde
    xp0, xp1 = xb1, xb1 - 1.0
    add_box(bm, ((xp0 + xp1) / 2, 0, zc + 0.1), (1.0, W - 0.1, 0.1), BLACK)
    add_box(bm, ((xp0 + xp1) / 2, 0, zc + 2.36), (1.1, W + 0.1, 0.1), BLACK)
    for s in (-1, 1):
        add_box(bm, ((xp0 + xp1) / 2, s * (W / 2 - 0.05), zc + 1.0), (1.0, 0.04,
                                                                     0.04), NICKEL)
        add_cylinder(bm, (xp1 + 0.05, s * (W / 2 - 0.05), zc + 1.2), 0.03, 2.3, 6,
                     NICKEL)
        _fender(bm, xr, s * (W / 2 - 0.25), r, 0.45, 165, 15, BLACK)
    obj = bpy.data.objects.new("PROTO_AUTOBUS_SCHNEIDER_H",
                               _finish(bm, "CARROSSERIE_autobus"))
    _materials(obj, M, car_paint("vert_autobus"), accent="creme")
    T = W - 0.5
    wheels = [(xf, T / 2), (xf, -T / 2), (xr, T / 2), (xr, -T / 2)]
    return obj, wheels, r


def build_fiacre(M):
    """Fiacre (victoria de place) et son cheval."""
    bm = bmesh.new()
    zc = 0.75
    add_box(bm, (-0.6, 0, zc + 0.35), (1.3, 1.2, 0.6), PAINT)          # caisse
    add_box(bm, (-0.75, 0, zc + 0.75), (0.5, 1.15, 0.25), LEATHER)
    add_sphere(bm, (-1.15, 0, zc + 1.15), 0.62, BLACK, 12, (0.6, 1.0, 0.9))
    add_box(bm, (0.55, 0, zc + 0.85), (0.5, 1.0, 0.12), LEATHER)       # siège cocher
    add_box(bm, (0.4, 0, zc + 0.4), (0.6, 0.9, 0.7), PAINT)
    for s in (-1, 1):
        add_box(bm, (2.0, s * 0.45, zc + 0.15), (2.6, 0.05, 0.05), BLACK)  # brancards
        _fender(bm, 0.6, s * 0.7, 0.42, 0.18, 150, 40, BLACK)
    # cheval (bai)
    hx = 2.4
    add_sphere(bm, (hx, 0, 1.45), 0.48, ACCENT, 12, (2.0, 0.85, 0.95))
    add_sphere(bm, (hx + 1.05, 0, 1.95), 0.22, ACCENT, 10, (1.2, 0.8, 1.9))
    add_sphere(bm, (hx + 1.35, 0, 2.2), 0.18, ACCENT, 10, (1.9, 0.7, 0.9))
    for dx in (-0.65, 0.65):
        for s in (-1, 1):
            add_cylinder(bm, (hx + dx, s * 0.2, 0.6), 0.07, 1.2, 6, ACCENT,
                         radius_top=0.1)
    add_cylinder(bm, (hx - 1.0, 0, 1.3), 0.06, 0.7, 6, BLACK, radius_top=0.03)
    # cocher en redingote et chapeau haut-de-forme
    add_cylinder(bm, (0.55, 0, zc + 1.25), 0.24, 0.75, 8, BLACK)
    add_sphere(bm, (0.55, 0, zc + 1.75), 0.11, LAMP, 8)
    add_cylinder(bm, (0.55, 0, zc + 1.95), 0.1, 0.22, 10, BLACK)
    obj = bpy.data.objects.new("PROTO_FIACRE",
                               _finish(bm, "CARROSSERIE_fiacre"))
    me = obj.data
    for m in (car_paint("noir"), M["capote"], M["nickel"], M["cuir"], M["vitre"],
              M["chair"], M["cheval"]):
        me.materials.append(m)
    wheels = [(0.6, 0.68), (0.6, -0.68), (-0.7, 0.68), (-0.7, -0.68)]
    return obj, wheels, 0.48


# --- Mise en scène -----------------------------------------------------------


class Fleet:
    def __init__(self, M, frame_obj):
        self.M = M
        self.frame = frame_obj
        self.root = collection("VEHICULES_1925")
        self.protos = collection("_PROTOTYPES_VEHICULES", self.root)
        self.protos.hide_render = True
        self.models = {}
        for spec in CARS:
            body, wheels = build_car_body(spec, M)
            self.protos.objects.link(body)
            wheel = _wheel_mesh(f"ROUE_{spec.key}", spec.wheel_r, M=M)
            self.models[spec.key] = (body, wheels, wheel, spec.wheel_r, spec)
        body, wheels, r = build_bus(M)
        self.protos.objects.link(body)
        self.models["autobus"] = (body, wheels, _wheel_mesh("ROUE_autobus", r,
                                                            wood=False, M=M),
                                  r, None)
        body, wheels, r = build_fiacre(M)
        self.protos.objects.link(body)
        self.models["fiacre"] = (body, wheels, _wheel_mesh("ROUE_fiacre", r,
                                                           spokes=14, M=M), r,
                                 None)
        self.count = 0

    def spawn(self, key, coll, paint=None, name=None):
        body, wheels, wheel_me, r, spec = self.models[key]
        self.count += 1
        name = name or f"{key.upper()}_{self.count:03d}"
        obj = bpy.data.objects.new(name, body.data)
        coll.objects.link(obj)
        if paint:
            obj.material_slots[PAINT].link = "OBJECT"
            obj.material_slots[PAINT].material = car_paint(paint)
        wheel_objs = []
        for i, (x, y) in enumerate(wheels):
            w = bpy.data.objects.new(f"{name}_ROUE_{i}", wheel_me)
            w.location = (x, y, r)
            w.parent = obj
            coll.objects.link(w)
            wheel_objs.append(w)
        return obj, wheel_objs, r

    def park(self, key, u, v, heading, paint=None, name=None):
        """Voiture à l'arrêt (repère place, cap en radians depuis +U)."""
        coll = collection("VEHICULES_STATIONNES", self.root)
        obj, _, _ = self.spawn(key, coll, paint, name)
        obj.location = (u, v, 0.0)
        obj.rotation_euler.z = heading
        obj.parent = self.frame
        return obj

    def drive(self, key, path_obj, path_len, f0, frames, paint=None, name=None,
              speed=None):
        """Voiture qui suit une trajectoire (contrainte Follow Path animée)."""
        coll = collection("VEHICULES_EN_CIRCULATION", self.root)
        obj, wheels, r = self.spawn(key, coll, paint, name)
        spec = self.models[key][4]
        v = speed or (spec.speed if spec else 6.0)
        fps = bpy.context.scene.render.fps
        df = v * (frames[1] - frames[0]) / fps / path_len
        c = obj.constraints.new("FOLLOW_PATH")
        c.target = path_obj
        c.use_curve_follow = True
        c.use_fixed_location = True
        c.forward_axis = "FORWARD_X"
        c.up_axis = "UP_Z"
        c.offset_factor = f0
        c.keyframe_insert("offset_factor", frame=frames[0])
        c.offset_factor = min(1.0, f0 + df)
        c.keyframe_insert("offset_factor", frame=frames[1])
        for fc in _fcurves(obj):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
        for w in wheels:
            d = w.driver_add("rotation_euler", 1).driver
            d.type = "SCRIPTED"
            var = d.variables.new()
            var.name = "f"
            var.type = "SINGLE_PROP"
            var.targets[0].id = obj
            var.targets[0].data_path = 'constraints["Follow Path"].offset_factor'
            d.expression = f"f * {path_len / r:.4f}"
        return obj


def _fcurves(obj):
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def make_path(name, points, coll, frame_obj):
    """Trajectoire (courbe POLY lissée) dans le repère place ; renvoie (objet, longueur)."""
    from mathutils import Vector
    pts = [Vector((x, y, 0.0)) for x, y in points]
    for _ in range(3):  # lissage de Chaikin
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out += [a.lerp(b, 0.25), a.lerp(b, 0.75)]
        out.append(pts[-1])
        pts = out
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.use_path = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts):
        p.co = (q.x, q.y, q.z, 1.0)
    obj = bpy.data.objects.new(name, cu)
    obj.hide_render = True
    link(obj, coll)
    length = sum((b - a).length for a, b in zip(pts, pts[1:]))
    return obj, length


# Trajectoires (repère place). Circulation à droite.
ROUTES = {
    # Champs-Élysées → rue de Rivoli (vers l'est), au sud de l'obélisque
    "CE_VERS_RIVOLI": [(-1100, -8), (-400, -8), (-110, -10), (-60, -22),
                       (0, -24), (60, -22), (96, -10), (98, 60),
                       (104, 140), (150, 148), (1300, 148)],
    # Quai des Tuileries → Champs-Élysées (vers l'ouest), au nord de l'obélisque
    "QUAI_VERS_CE": [(1200, -187), (800, -214), (500, -186), (300, -165),
                     (150, -155), (110, -120), (97, -60), (96, 24), (60, 24),
                     (0, 26), (-60, 24), (-110, 10), (-400, 8), (-1100, 8)],
    # Rue Royale → pont de la Concorde (vers le sud), à l'ouest de l'axe
    "ROYALE_VERS_PONT": [(-6, 650), (-6, 200), (-8, 135), (-24, 62),
                         (-24, 30), (-24, -30), (-24, -62), (-6, -135),
                         (-5, -300), (-5, -335), (-60, -345), (-200, -380),
                         (-400, -500)],
    # Pont → rue Royale (vers le nord), à l'est de l'axe
    "PONT_VERS_ROYALE": [(300, -365), (80, -345), (5, -338), (5, -150),
                         (24, -62), (24, -30), (24, 30), (24, 62), (8, 135),
                         (6, 200), (6, 650)],
    # Devant les palais de Gabriel (vers l'ouest), puis avenue Gabriel
    "GABRIEL_OUEST": [(600, 150), (150, 152), (60, 156), (-60, 156),
                      (-150, 152), (-260, 155), (-900, 170)],
    # Cours la Reine / quai (vers l'est)
    "COURS_LA_REINE_EST": [(-900, -650), (-700, -515), (-450, -325),
                           (-300, -240), (-150, -168), (0, -162), (150, -165),
                           (300, -175), (500, -196), (800, -224),
                           (1200, -197)],
}


def populate(fleet, M, frame_obj, frames=(1, 240), seed=1925):
    rnd = random.Random(seed)
    paths = collection("TRAJECTOIRES", fleet.root)
    car_keys = [s.key for s in CARS]
    weights = [3, 3, 4, 2, 2, 1, 1]  # beaucoup de taxis et de petites Citroën
    for rname, pts in ROUTES.items():
        path, length = make_path(f"TRAJ_{rname}", pts, paths, frame_obj)
        n = max(4, int(length / 55))
        slots = sorted(rnd.uniform(0.0, 0.9) for _ in range(n))
        for k, f0 in enumerate(slots):
            if rname in ("CE_VERS_RIVOLI", "QUAI_VERS_CE") and k == 1:
                key = "autobus"
            elif rname == "GABRIEL_OUEST" and k == 2:
                key = "fiacre"
            else:
                key = rnd.choices(car_keys, weights)[0]
            spec = fleet.models[key][4]
            paint = rnd.choice(spec.paints) if spec else None
            fleet.drive(key, path, length, f0, frames, paint=paint,
                        speed=(spec.speed if spec else (3.0 if key == "fiacre"
                                                        else 7.0))
                        * rnd.uniform(0.8, 1.15))
    # Devant le Crillon : taxis en attente, voiture de maître, fourgonnette
    v = geo.GABRIEL_FACADE_V - 9.6
    fleet.park("taxi_g7", -100, v, math.pi, "rouge_taxi", "TAXI_G7_ATTENTE_1")
    fleet.park("taxi_g7", -94.5, v, math.pi, "rouge_taxi", "TAXI_G7_ATTENTE_2")
    fleet.park("hispano_h6", -82, v, math.pi, "bordeaux",
               "HISPANO_SUIZA_DEVANT_LE_CRILLON")
    fleet.park("citroen_b12", -70, v, math.pi, "noir")
    fleet.park("fourgonnette", -45, v, math.pi, "vert_bouteille")
    fleet.park("renault_nn", 60, v, math.pi, "gris_taupe")
    fleet.park("ford_t", 72, v, math.pi, "noir")
