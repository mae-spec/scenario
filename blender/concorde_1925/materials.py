"""Matériaux procéduraux (aucune texture externe : le .blend est autonome).

Palette volontairement « 1925 » : en 1925 la pierre de Paris n'a pas été
ravalée depuis des décennies (les grands nettoyages datent de la loi Malraux,
1962) ; elle est grise et noircie par la suie, surtout dans les creux.
"""
from __future__ import annotations

import bpy

_cache: dict[str, bpy.types.Material] = {}


def _bsdf(mat):
    nt = mat.node_tree
    return nt, nt.nodes["Principled BSDF"]


def principled(name: str, color, roughness: float = 0.6, metallic: float = 0.0,
               variation: float = 0.0, var_scale: float = 4.0,
               bump: float = 0.0, bump_scale: float = 30.0,
               emission=None, emission_strength: float = 0.0,
               transmission: float = 0.0, ior: float = 1.45,
               alpha: float = 1.0, coat: float = 0.0,
               subsurface: float = 0.0) -> bpy.types.Material:
    if name in _cache:
        return _cache[name]
    mat = bpy.data.materials.new(name)
    nt, bsdf = _bsdf(mat)
    links = nt.links
    c = (*color[:3], 1.0)
    bsdf.inputs["Base Color"].default_value = c
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["IOR"].default_value = ior
    if transmission:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.08
    if subsurface:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission[:3], 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    coord = None
    if variation or bump:
        coord = nt.nodes.new("ShaderNodeTexCoord")
    if variation:
        # Salissures / variations de teinte à grande échelle.
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = var_scale
        noise.inputs["Detail"].default_value = 6.0
        links.new(coord.outputs["Object"], noise.inputs["Vector"])
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        dark = [max(0.0, x * (1.0 - variation)) for x in color[:3]]
        ramp.color_ramp.elements[0].color = (*dark, 1.0)
        ramp.color_ramp.elements[1].color = c
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.65
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if bump:
        bnoise = nt.nodes.new("ShaderNodeTexNoise")
        bnoise.inputs["Scale"].default_value = bump_scale
        bnoise.inputs["Detail"].default_value = 8.0
        links.new(coord.outputs["Object"], bnoise.inputs["Vector"])
        bnode = nt.nodes.new("ShaderNodeBump")
        bnode.inputs["Strength"].default_value = bump
        bnode.inputs["Distance"].default_value = 0.02
        links.new(bnoise.outputs["Fac"], bnode.inputs["Height"])
        links.new(bnode.outputs["Normal"], bsdf.inputs["Normal"])
    _cache[name] = mat
    return mat


def facade_windows(name: str, wall, frame_dark=(0.05, 0.05, 0.06),
                   bay: float = 3.1, storey: float = 3.4,
                   ground_floor: float = 4.5) -> bpy.types.Material:
    """Façade d'immeuble avec grille de fenêtres procédurale.

    Les fenêtres sont calculées dans l'espace objet : u = x + y le long de la
    façade (valable pour des blocs alignés sur leurs axes locaux), z = étage.
    """
    if name in _cache:
        return _cache[name]
    mat = bpy.data.materials.new(name)
    nt, bsdf = _bsdf(mat)
    N, L = nt.nodes, nt.links
    coord = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(coord.outputs["Object"], sep.inputs[0])

    def math(op, a, b=None, v=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        for i, x in enumerate((a, b)):
            if x is None:
                continue
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                L.new(x, n.inputs[i])
        if v is not None:
            n.inputs[1].default_value = v
        return n.outputs[0]

    horiz = math("ADD", sep.outputs["X"], sep.outputs["Y"])
    fu = math("FRACT", math("DIVIDE", horiz, bay))
    zz = math("SUBTRACT", sep.outputs["Z"], ground_floor)
    fz = math("FRACT", math("DIVIDE", zz, storey))
    in_u = math("MULTIPLY", math("GREATER_THAN", fu, 0.3),
                math("LESS_THAN", fu, 0.7))
    in_z = math("MULTIPLY", math("GREATER_THAN", fz, 0.18),
                math("LESS_THAN", fz, 0.82))
    above_shop = math("GREATER_THAN", zz, 0.0)
    win = math("MULTIPLY", math("MULTIPLY", in_u, in_z), above_shop)
    # Salissure de la pierre
    noise = N.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.35
    L.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*[x * 0.6 for x in wall], 1)
    ramp.color_ramp.elements[1].color = (*wall, 1)
    L.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    L.new(win, mix.inputs["Factor"])
    L.new(ramp.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = (*frame_dark, 1)
    L.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    rough = N.new("ShaderNodeMapRange")
    L.new(win, rough.inputs["Value"])
    rough.inputs["To Min"].default_value = 0.85
    rough.inputs["To Max"].default_value = 0.12
    L.new(rough.outputs["Result"], bsdf.inputs["Roughness"])
    _cache[name] = mat
    return mat


def library() -> dict[str, bpy.types.Material]:
    """Tous les matériaux de la scène, par nom court."""
    stone = (0.42, 0.39, 0.34)
    return {
        "pierre": principled("PIERRE_PARIS_1925", stone, 0.85,
                             variation=0.45, var_scale=0.6, bump=0.25),
        "pierre_claire": principled("PIERRE_CLAIRE", (0.52, 0.49, 0.43), 0.8,
                                    variation=0.3, var_scale=0.8, bump=0.2),
        "ardoise": principled("ARDOISE", (0.12, 0.13, 0.15), 0.55,
                              variation=0.3, bump=0.1, bump_scale=8),
        "zinc": principled("ZINC_TOITURE", (0.38, 0.40, 0.43), 0.45, 0.6,
                           variation=0.3, var_scale=1.5),
        "chaussee": principled("CHAUSSEE_MACADAM", (0.20, 0.195, 0.18), 0.9,
                               variation=0.35, var_scale=0.08, bump=0.15),
        "trottoir": principled("TROTTOIR_PIERRE", (0.36, 0.34, 0.31), 0.85,
                               variation=0.25, var_scale=0.3, bump=0.1),
        "pave": principled("PAVES_GRES", (0.33, 0.31, 0.29), 0.8,
                           variation=0.3, bump=0.6, bump_scale=6),
        "granit": principled("GRANIT_ROSE_SYENE", (0.47, 0.33, 0.29), 0.5,
                             variation=0.25, var_scale=3, bump=0.3,
                             bump_scale=60),
        "bronze": principled("FONTE_PATINE_BRONZE", (0.10, 0.12, 0.09), 0.45,
                             0.85, variation=0.4, var_scale=2.0),
        "dorure": principled("DORURE", (0.80, 0.60, 0.25), 0.3, 1.0),
        "eau": principled("EAU_BASSIN", (0.05, 0.08, 0.07), 0.04,
                          transmission=0.0, ior=1.33, bump=0.15,
                          bump_scale=4),
        "nappe": principled("NAPPE_EAU_FONTAINE", (0.8, 0.85, 0.85), 0.12,
                            transmission=1.0, ior=1.33, alpha=0.6),
        "seine": principled("EAU_SEINE", (0.06, 0.08, 0.06), 0.08,
                            bump=0.3, bump_scale=0.6),
        "feuillage": principled("FEUILLAGE_MARRONNIER", (0.10, 0.17, 0.05),
                                0.7, variation=0.5, var_scale=0.5, bump=0.8,
                                bump_scale=3, subsurface=0.1),
        "ecorce": principled("ECORCE", (0.12, 0.10, 0.08), 0.9, bump=0.5),
        "pelouse": principled("PELOUSE", (0.13, 0.20, 0.06), 0.9,
                              variation=0.4, var_scale=0.2),
        "gravier": principled("GRAVIER_JARDIN", (0.55, 0.50, 0.42), 0.95,
                              variation=0.2, bump=0.2, bump_scale=40),
        "vitre": principled("VITRE", (0.02, 0.025, 0.03), 0.05, 0.0,
                            coat=1.0),
        "fonte": principled("FONTE_LAMPADAIRE", (0.04, 0.05, 0.04), 0.5, 0.7),
        "globe": principled("GLOBE_VERRE", (0.85, 0.85, 0.8), 0.2,
                            transmission=0.6, emission=(1.0, 0.75, 0.45),
                            emission_strength=0.0),
        "facade": facade_windows("FACADE_HAUSSMANN", (0.46, 0.43, 0.37)),
        "facade_sombre": facade_windows("FACADE_HAUSSMANN_SOMBRE",
                                        (0.36, 0.33, 0.29)),
        "verriere": principled("VERRIERE_GRAND_PALAIS", (0.35, 0.42, 0.40),
                               0.2, 0.5),
        "metal_eiffel": principled("FER_TOUR_EIFFEL", (0.30, 0.20, 0.13), 0.7,
                                   0.4),
        "drapeau_bleu": principled("DRAPEAU_BLEU", (0.02, 0.05, 0.35), 0.8),
        "drapeau_blanc": principled("DRAPEAU_BLANC", (0.8, 0.8, 0.78), 0.8),
        "drapeau_rouge": principled("DRAPEAU_ROUGE", (0.55, 0.03, 0.03), 0.8),
        # Véhicules
        "nickel": principled("NICKEL_POLI", (0.75, 0.72, 0.65), 0.15, 1.0),
        "pneu": principled("PNEU_CAOUTCHOUC", (0.04, 0.04, 0.04), 0.75),
        "capote": principled("CAPOTE_TOILE", (0.03, 0.03, 0.03), 0.8,
                             bump=0.2, bump_scale=80),
        "cuir": principled("CUIR_SIEGE", (0.20, 0.08, 0.04), 0.5),
        "bois_roue": principled("BOIS_ROUE_ARTILLERIE", (0.30, 0.17, 0.08),
                                0.4, coat=0.5),
        "phare": principled("VERRE_PHARE", (0.9, 0.9, 0.85), 0.05,
                            emission=(1.0, 0.85, 0.6), emission_strength=0.0),
        # Chambre du Crillon
        "parquet": principled("PARQUET_VERSAILLES", (0.30, 0.17, 0.08), 0.35,
                              variation=0.35, var_scale=6, coat=0.4),
        "boiserie": principled("BOISERIE_LAQUEE", (0.62, 0.60, 0.53), 0.45,
                               variation=0.1),
        "moulure_or": principled("MOULURE_DOREE", (0.75, 0.55, 0.22), 0.35,
                                 1.0),
        "velours": principled("VELOURS_RIDEAU", (0.32, 0.05, 0.06), 0.9,
                              variation=0.4, var_scale=8, subsurface=0.05),
        "voilage": principled("VOILAGE", (0.9, 0.88, 0.82), 0.7,
                              transmission=0.7, alpha=0.55),
        "tapis": principled("TAPIS_SAVONNERIE", (0.35, 0.22, 0.14), 0.95,
                            variation=0.5, var_scale=12),
        "tissu": principled("TISSU_FAUTEUIL", (0.55, 0.45, 0.28), 0.85,
                            variation=0.2),
        "marbre": principled("MARBRE_CHEMINEE", (0.85, 0.83, 0.80), 0.15,
                             variation=0.15, var_scale=10),
        "personne": principled("SILHOUETTE_VETEMENT", (0.05, 0.05, 0.06),
                               0.8),
        "chair": principled("CHAIR", (0.60, 0.42, 0.33), 0.6,
                            subsurface=0.2),
        "chapeau": principled("FEUTRE_CHAPEAU", (0.08, 0.07, 0.06), 0.8),
        "cheval": principled("ROBE_CHEVAL", (0.18, 0.10, 0.05), 0.6),
    }


CAR_PAINTS = {
    "noir": (0.012, 0.012, 0.014),
    "vert_bouteille": (0.02, 0.07, 0.04),
    "bordeaux": (0.18, 0.02, 0.03),
    "bleu_nuit": (0.02, 0.03, 0.10),
    "gris_taupe": (0.16, 0.14, 0.12),
    "creme": (0.65, 0.58, 0.42),
    "rouge_taxi": (0.35, 0.04, 0.03),
    "jaune_citron": (0.65, 0.48, 0.06),
    "vert_autobus": (0.05, 0.16, 0.08),
}


def car_paint(key: str) -> bpy.types.Material:
    return principled(f"PEINTURE_{key.upper()}", CAR_PAINTS[key], 0.35,
                      coat=0.8, variation=0.08, var_scale=1.0)
