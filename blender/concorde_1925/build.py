"""Génère la scène « Place de la Concorde, juin 1925 ».

Usage :
    blender -b -P blender/concorde_1925/build.py -- --out concorde_1925.blend
    blender -b -P blender/concorde_1925/build.py -- --out c.blend --previews apercus/

Options :
    --out FICHIER      .blend à écrire (défaut : concorde_1925.blend à côté du script)
    --previews DOSSIER rend une image basse définition par caméra
    --preview-scale N  pourcentage de la résolution 6560 × 2733 (défaut 12)
    --preview-samples  échantillons Cycles des aperçus (défaut 32)
    --frames N         durée du plan en images à 24 i/s (défaut 240)
    --no-haze          sans volume de brume
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import bpy  # noqa: E402

import architecture  # noqa: E402
import city  # noqa: E402
import geo  # noqa: E402
import monuments  # noqa: E402
import scene_setup  # noqa: E402
import vegetation  # noqa: E402
import vehicles  # noqa: E402
from helpers import collection, set_frame  # noqa: E402
from materials import library  # noqa: E402


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="build.py")
    p.add_argument("--out", default=os.path.join(HERE, "concorde_1925.blend"))
    p.add_argument("--previews")
    p.add_argument("--preview-scale", type=int, default=12)
    p.add_argument("--preview-samples", type=int, default=32)
    p.add_argument("--frames", type=int, default=240)
    p.add_argument("--no-haze", action="store_true")
    return p.parse_args(argv)


def _step(msg, t0=[time.time()]):
    print(f"[concorde 1925] {time.time() - t0[0]:6.1f} s  {msg}", flush=True)


def build(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "PLACE_DE_LA_CONCORDE_1925"
    frames = (1, args.frames)
    scene_setup.render_settings(scene, frames)

    frame = bpy.data.objects.new("REPERE_PLACE", None)
    frame.empty_display_type = "ARROWS"
    frame.empty_display_size = 20
    # +V (axe rue Royale) doit pointer à l'azimut 25,6° : rotation horaire.
    frame.rotation_euler.z = -math.radians(geo.AXIS_AZIMUTH_DEG)
    frame["note"] = ("Repère place : origine = obélisque ; +Y local = axe rue "
                     "Royale/Madeleine ; monde +Y = nord géographique")
    scene.collection.objects.link(frame)
    set_frame(frame)

    M = library()
    c_terrain = collection("TERRAIN_SEINE")
    c_place = collection("PLACE_AMENAGEMENTS")
    c_mon = collection("MONUMENTS")
    c_bat = collection("BATIMENTS")
    c_room = collection("CHAMBRE_CRILLON_2E")
    c_veg = collection("VEGETATION")
    c_cam = collection("CAMERAS_ALEXA65")
    c_light = collection("LUMIERES_ATMOSPHERE")

    _step("sol, Seine et ponts")
    city.ground_and_river(c_terrain, M)
    city.bridges(c_terrain, M)

    _step("aménagement de la place")
    lamp_pts, rostral_pts, vertices = city.place_layout(c_place, M)
    monuments.street_furniture(c_place, M, [lamp_pts], rostral_pts)
    for v, name in zip(vertices, geo.PLACE_INNER_STATUES):
        rot = math.atan2(-v.y, -v.x) - math.pi / 2  # la statue regarde l'obélisque
        monuments.statue_pavilion(c_mon, M, f"STATUE_{name.upper()}", v.x, v.y,
                                  rot)
    monuments.scatter_people(c_place, M, [
        (-170, 170, geo.GABRIEL_FACADE_V - 7.5, geo.GABRIEL_FACADE_V - 1),
        (-80, 80, 77, 84), (-80, 80, -84, -77),
        (-15, 15, -11, 11), (-12, 12, 52, 76), (-12, 12, -76, -52)], 140)

    _step("monuments")
    monuments.obelisk(c_mon, M)
    monuments.fountain(c_mon, M, "FONTAINE_DES_FLEUVES", geo.FOUNTAIN_NORTH_V)
    monuments.fountain(c_mon, M, "FONTAINE_DES_MERS", geo.FOUNTAIN_SOUTH_V)
    city.marly_horses(c_mon, M)
    city.tuileries_entrance(c_bat, M)
    city.landmarks(c_bat, M)

    _step("palais de Gabriel et chambre du Crillon")
    hw = geo.RUE_ROYALE_HALF_W
    room = architecture.gabriel_palace(
        c_bat, M, "PALAIS_GABRIEL_OUEST_ACF_CRILLON",
        -hw - geo.GABRIEL_WIDTH, -hw, room_bay=architecture.ROOM_BAY)
    architecture.gabriel_palace(c_bat, M, "PALAIS_GABRIEL_EST_HOTEL_DE_LA_MARINE",
                                hw, hw + geo.GABRIEL_WIDTH)
    eye, _ = architecture.crillon_room(c_room, M, room["u"])

    _step("îlots urbains")
    n_blocks = city.city_blocks(c_bat, M)
    _step(f"  {n_blocks} îlots")

    _step("arbres")
    n_trees = vegetation.plant(c_veg, M)
    _step(f"  {n_trees} arbres")

    _step("véhicules 1925")
    fleet = vehicles.Fleet(M, frame)
    vehicles.populate(fleet, M, frame, frames)

    _step("caméras, soleil, ciel")
    cams = scene_setup.cameras(c_cam, eye, (room["u"], room["v"]))
    scene.camera = cams["CAM_01_CARTE_POSTALE"]
    _, az, alt = scene_setup.sun_and_sky(c_light, frame)
    _step(f"  soleil : azimut {az:.1f}°, hauteur {alt:.1f}°")
    scene_setup.room_fill(c_light, room["u"], room["v"])
    if not args.no_haze:
        scene_setup.haze(c_light, M)
    scene.frame_set(1)
    return cams


def previews(cams, folder, scale, samples):
    os.makedirs(folder, exist_ok=True)
    scene = bpy.context.scene
    keep = (scene.render.resolution_percentage,
            getattr(scene.cycles, "samples", None))
    scene.render.resolution_percentage = scale
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.device = "CPU"
    scene.render.image_settings.file_format = "JPEG"
    for name, cam in cams.items():
        scene.camera = cam
        scene.render.filepath = os.path.join(folder, f"{name}.jpg")
        _step(f"rendu {name}")
        bpy.ops.render.render(write_still=True)
    scene.render.resolution_percentage = keep[0]
    if keep[1] is not None:
        scene.cycles.samples = keep[1]
        scene.cycles.device = "GPU"
    scene.camera = cams["CAM_01_CARTE_POSTALE"]


def main():
    args = _args()
    cams = build(args)
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    _step(f"scène enregistrée : {out}")
    if args.previews:
        previews(cams, args.previews, args.preview_scale, args.preview_samples)


if __name__ == "__main__":
    main()
