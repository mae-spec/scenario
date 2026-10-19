"""Caméras ARRI Alexa 65 (2,40:1), soleil du 12 juin 1925, ciel, brume, rendu."""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Euler, Vector

import geo
from helpers import add_box, link, object_from_bmesh

# ARRI Alexa 65 — capteur A3X « Open Gate » 54,12 × 25,58 mm (6560 × 3100 px).
# Extraction 2,40:1 sur toute la largeur : 54,12 × 22,55 mm → 6560 × 2733 px.
ALEXA65_SENSOR_W = 54.12
ALEXA65_SENSOR_H_240 = ALEXA65_SENSOR_W / 2.40
ALEXA65_RES = (6560, 2733)


def alexa65_camera(coll, name, eye, target, lens_mm, fstop=5.6,
                   focus=None, shift_y=0.0):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = ALEXA65_SENSOR_W
    cam.sensor_height = ALEXA65_SENSOR_H_240
    cam.lens = lens_mm
    cam.shift_y = shift_y
    cam.clip_start = 0.05
    cam.clip_end = 8000.0
    cam.show_passepartout = True
    cam.passepartout_alpha = 0.9
    cam.show_composition_thirds = True
    eye_v, tgt_v = Vector(eye), Vector(target)
    cam.dof.use_dof = True
    cam.dof.aperture_fstop = fstop
    cam.dof.focus_distance = focus or (tgt_v - eye_v).length
    cam.dof.aperture_blades = 9
    obj = bpy.data.objects.new(name, cam)
    obj.location = eye_v
    obj.rotation_euler = (tgt_v - eye_v).to_track_quat("-Z", "Y").to_euler()
    obj["objectif"] = f"ARRI Prime 65 {lens_mm:.0f} mm — T{fstop}"
    obj["capteur"] = "ARRI Alexa 65, Open Gate 54,12 mm, extraction 2,40:1"
    return link(obj, coll)


def cameras(coll, room_eye, room_window):
    """Plans prévus ; tous les points sont dans le repère place (m)."""
    F = geo.GABRIEL_FACADE_V
    wu, wv = room_window
    cams = {}
    # 1. La carte postale « A C. 17 » : prise du toit de l'Hôtel de la Marine,
    #    plongée vers le sud (obélisque, Fontaine des Fleuves, pont,
    #    Palais-Bourbon, dôme des Invalides).
    cams["CAM_01_CARTE_POSTALE"] = alexa65_camera(
        coll, "CAM_01_CARTE_POSTALE", (34.0, F + 1.0, 27.5),
        (-2.0, -240.0, -32.0), 55, fstop=8)
    # 2. Contrechamp large, depuis le refuge sud de l'obélisque, vers le nord :
    #    Crillon à gauche, rue Royale et la Madeleine, Hôtel de la Marine à droite.
    cams["CAM_02_CONTRECHAMP_LARGE"] = alexa65_camera(
        coll, "CAM_02_CONTRECHAMP_LARGE", (-30.0, -25.0, 1.7),
        (-22.0, F, 11.0), 45, fstop=5.6, shift_y=0.06)
    # 3. Contrechamp serré sur la façade du Crillon : cadre la fenêtre de la
    #    chambre du 2e étage (raccord avec les plans 4 et 5).
    cams["CAM_03_CONTRECHAMP_CRILLON"] = alexa65_camera(
        coll, "CAM_03_CONTRECHAMP_CRILLON", (-48.0, 62.0, 1.6),
        (wu, wv, geo.GABRIEL_FLOOR_2 + 1.2), 80, fstop=4)
    # 4. Dans la chambre, de dos, la fenêtre ouverte et la place au loin.
    cams["CAM_04_CHAMBRE_CRILLON"] = alexa65_camera(
        coll, "CAM_04_CHAMBRE_CRILLON", room_eye,
        (wu - 0.4, wv - 20.0, geo.GABRIEL_FLOOR_2 - 1.0), 35, fstop=4,
        focus=7.0)
    # 5. Le regard du personnage à la fenêtre : la place à travers la colonnade.
    #    L'œil est décalé de 50 cm vers l'ouest dans l'embrasure : depuis le
    #    milieu de la fenêtre, la colonne est de cette travée cache l'obélisque.
    pov_eye = (wu - 0.5, wv + 0.75, geo.GABRIEL_FLOOR_2 + 1.62)
    cams["CAM_05_VUE_FENETRE_2E"] = alexa65_camera(
        coll, "CAM_05_VUE_FENETRE_2E", pov_eye, (-30.0, 0.0, -4.0), 40,
        fstop=5.6, focus=190.0)
    return cams


def sun_and_sky(coll, frame_obj):
    az, alt = geo.sun_direction(*geo.SHOOT_DATE, geo.SHOOT_LOCAL_TIME,
                                geo.SHOOT_UTC_OFFSET)
    a, e = math.radians(az), math.radians(alt)
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e),
                     math.sin(e)))  # monde : +X est, +Y nord
    sun = bpy.data.lights.new("SOLEIL_12_JUIN_1925_15H30", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(0.53)
    sun.color = (1.0, 0.96, 0.9)
    obj = bpy.data.objects.new("SOLEIL_12_JUIN_1925_15H30", sun)
    obj.rotation_euler = to_sun.to_track_quat("Z", "Y").to_euler()
    obj.location = to_sun * 300
    obj["azimut_deg"] = round(az, 2)
    obj["hauteur_deg"] = round(alt, 2)
    link(obj, coll, in_place_frame=False)

    world = bpy.data.worlds.new("CIEL_PARIS_1925")
    bpy.context.scene.world = world
    if hasattr(world, "use_nodes") and not world.node_tree:
        world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    sky = nt.nodes.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = e
    # sun_rotation = azimut compté depuis +Y (nord), sens horaire
    # (vérifié par un rendu panoramique avec le disque solaire).
    sky.sun_rotation = a
    sky.sun_disc = False  # le disque est porté par la lampe « soleil »
    sky.air_density = 1.0
    sky.aerosol_density = 2.0   # air chargé de fumées de charbon
    sky.ozone_density = 1.0
    sky.altitude = 35.0
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.3
    out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return obj, az, alt


def haze(coll, M, density=0.0001):
    """Brume urbaine (volume) : les lointains se fondent comme sur la photo."""
    bm = bmesh.new()
    add_box(bm, (0, 0, 280), (7000, 7000, 600), 0)
    obj = object_from_bmesh("BRUME_PARIS_1925", bm, coll)
    mat = bpy.data.materials.new("VOLUME_BRUME")
    nt = mat.node_tree
    nt.nodes.clear()
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Color"].default_value = (0.82, 0.8, 0.74, 1)
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = 0.35
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    obj.data.materials.append(mat)
    obj.display_type = "BOUNDS"
    obj.visible_shadow = False
    return obj


def room_fill(coll, window_u, window_v):
    """Rebond de lumière dans la chambre (porte la lumière du ciel)."""
    lt = bpy.data.lights.new("REBOND_FENETRE_CHAMBRE", "AREA")
    lt.shape = "RECTANGLE"
    lt.size, lt.size_y = 1.7, 2.4
    lt.energy = 900.0
    lt.color = (0.85, 0.9, 1.0)
    obj = bpy.data.objects.new("REBOND_FENETRE_CHAMBRE", lt)
    obj.location = (window_u, window_v + 0.75, geo.GABRIEL_FLOOR_2 + 1.6)
    obj.rotation_euler = Euler((math.radians(90), 0, 0))  # éclaire vers +V
    obj.visible_camera = False
    return link(obj, coll)


def render_settings(scene, frames):
    try:
        import addon_utils
        addon_utils.enable("cycles", default_set=True)
    except Exception:  # Blender complet : Cycles est déjà là
        pass
    try:
        scene.render.engine = "CYCLES"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 256
        scene.cycles.use_denoising = True
        scene.cycles.max_bounces = 8
        scene.cycles.volume_bounces = 1
        scene.cycles.device = "GPU"
    scene.render.resolution_x, scene.render.resolution_y = ALEXA65_RES
    scene.render.resolution_percentage = 100
    scene.render.pixel_aspect_x = scene.render.pixel_aspect_y = 1.0
    scene.render.fps = 24
    scene.frame_start, scene.frame_end = frames
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5  # obturateur 180°
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.5
    scene.unit_settings.system = "METRIC"
    scene.render.metadata_input = "SCENE"
    scene.render.use_stamp_lens = True
    scene.render.use_stamp_camera = True
