"""Géographie de la place de la Concorde (état 1925).

Repère « place » (en mètres) :
  - origine : centre de l'obélisque, au niveau de la chaussée ;
  - axe +V : axe rue Royale → Madeleine (vers le nord-nord-est) ;
  - axe +U : axe historique vers les Tuileries / le Louvre (vers l'est-sud-est) ;
  - Z : altitude au-dessus de la chaussée.

Le repère place est tourné par rapport au nord géographique : l'axe rue Royale /
Palais-Bourbon a un azimut d'environ 25,6° (il est perpendiculaire à l'axe
historique Louvre → Arc de Triomphe, azimut ≈ 295,6°). Dans le .blend, +Y monde =
nord géographique et +X monde = est ; l'objet vide « REPERE_PLACE » porte cette
rotation, ce qui garantit une course du soleil juste.

Les positions ci-dessous sont dérivées des coordonnées WGS84 des monuments
(projection locale équirectangulaire) et des dimensions publiées. Elles sont
justes à quelques mètres près : à recaler sur un relevé (cadastre, OSM, IGN)
si un plan précis est nécessaire.
"""
from __future__ import annotations

import math

# Obélisque de Louxor (coordonnée fournie par la production)
LAT0 = 48.8654948
LON0 = 2.3211384
AXIS_AZIMUTH_DEG = 25.6  # azimut de +V (0° = nord, sens horaire)

M_PER_DEG_LAT = 111_200.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(LAT0))


def latlon_to_place(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 → (u, v) en mètres dans le repère place."""
    east = (lon - LON0) * M_PER_DEG_LON
    north = (lat - LAT0) * M_PER_DEG_LAT
    a = math.radians(AXIS_AZIMUTH_DEG)
    u = east * math.cos(a) - north * math.sin(a)
    v = east * math.sin(a) + north * math.cos(a)
    return u, v


# --- La place ---------------------------------------------------------------
# La place mesure 212 m d'est en ouest (de la grille des Tuileries aux chevaux
# de Marly) et 359 m du nord au sud (des façades de Gabriel au parapet de la
# Seine). Positions de contrôle, en mètres dans le repère place :
#   grille des Tuileries / pont tournant (48,865089 N ; 2,322375 E) → u = +101
#   Renommée de Coysevox (48,865278 N ; 2,322500 E)               → (100, 21)
#   statue de Strasbourg (48,86580 N ; 2,32270 E)                  → (88, 80)
#   statue de Brest (48,86650 N ; 2,32060 E)                       → (-84, 84)
#   statue de Lille (48,86620 N ; 2,32270 E)                       → (69, 120)
#   statue de Rouen (48,86670 N ; 2,32100 E)                       → (-68, 119)
#   statue de Marseille (48,864223 N ; 2,321256 E)                 → (68, -122)
# Emprise de la place, anciens fossés compris (comblés en 1854).
PLACE_HALF_U = 106.0
PLACE_HALF_V = 140.0
# Octogone intérieur bordé de balustrades ; les guérites des huit statues des
# villes occupent ses sommets (ordre trigonométrique depuis le sud-est).
PLACE_INNER = [(69.0, -120.0), (87.0, -81.0), (87.0, 81.0), (69.0, 120.0),
               (-69.0, 120.0), (-87.0, 81.0), (-87.0, -81.0), (-69.0, -120.0)]
PLACE_INNER_STATUES = ("Marseille", "Lyon", "Strasbourg", "Lille",
                       "Rouen", "Brest", "Nantes", "Bordeaux")
TUILERIES_GATE_U = 101.0
MARLY_U = -110.0

# Fontaines de Hittorff (1840), sur l'axe rue Royale / pont
# (Fontaine des Fleuves : 48,865992 N ; 2,321506 E).
FOUNTAIN_NORTH_V = 62.0   # Fontaine des Fleuves
FOUNTAIN_SOUTH_V = -62.0  # Fontaine des Mers

# Obélisque (sans le pyramidion doré, posé en 1998).
OBELISK_SHAFT_H = 22.83
OBELISK_BASE_SIDE = 2.42
OBELISK_TOP_SIDE = 1.54
OBELISK_PEDESTAL_H = 9.2

# --- Palais de Gabriel (Hôtel de la Marine à l'est, Crillon à l'ouest) ------
# Façade sur la place (plan des colonnes) et profondeur des bâtiments.
# Repères : Hôtel de la Marine (48,866778 N ; 2,323083 E) → (67, 190) et
# Crillon (48,867337 N ; 2,321149 E) → (-88, 185) ; la façade ferme la place à
# 176 m au nord (359 m jusqu'au parapet de la Seine).
GABRIEL_FACADE_V = 176.0
GABRIEL_DEPTH = 75.0
RUE_ROYALE_HALF_W = 14.0
GABRIEL_WIDTH = 96.0  # chaque palais
# Le palais ouest abrite l'Automobile Club de France (n° 6-8, côté rue Royale)
# et l'Hôtel de Crillon (n° 10, côté rue Boissy-d'Anglas).
CRILLON_U_RANGE = (-RUE_ROYALE_HALF_W - GABRIEL_WIDTH, -RUE_ROYALE_HALF_W - 44.0)

# Élévation (m au-dessus de la chaussée)
GABRIEL_ARCADE_TOP = 8.6        # rez-de-chaussée à arcades / soubassement
GABRIEL_FLOOR_1 = 8.9           # 1er étage (étage noble)
GABRIEL_FLOOR_2 = 14.6          # 2e étage (fenêtres carrées derrière la colonnade)
GABRIEL_COLUMN_TOP = 20.4
GABRIEL_CORNICE_TOP = 22.6
GABRIEL_BALUSTRADE_TOP = 24.0
GABRIEL_LOGGIA_DEPTH = 3.6      # galerie entre colonnes et mur des fenêtres

# --- Repères lointains -------------------------------------------------------
# Axe de la Seine (WGS84, d'amont en aval), largeur entre parapets.
SEINE_AXIS_LATLON = (
    (48.85840, 2.33400),  # pont du Carrousel
    (48.85960, 2.32900),  # pont Royal
    (48.86160, 2.32420),  # passerelle Solférino
    (48.86346, 2.32000),  # pont de la Concorde (centre : 48,8635 N ; 2,3196 E)
    (48.86380, 2.31700),
    (48.86370, 2.31350),  # pont Alexandre-III
    (48.86300, 2.30980),  # pont des Invalides
    (48.86250, 2.30140),  # pont de l'Alma
    (48.86000, 2.29250),  # pont d'Iéna
    (48.85600, 2.28600),  # Bir-Hakeim
)
SEINE_WIDTH = 135.0
SEINE_LEVEL = -8.5
PONT_CONCORDE_WIDTH = 15.5      # largeur d'origine (élargi à 35 m en 1930-1932)
PALAIS_BOURBON_PORTICO_V = -365.0  # centre du palais : 48,862069 N ; 2,318681 E
MADELEINE_V = latlon_to_place(48.87003, 2.32447)[1]  # centre de l'église
INVALIDES_DOME = latlon_to_place(48.85500, 2.31250)
TOUR_EIFFEL = latlon_to_place(48.85837, 2.29448)
GRAND_PALAIS = latlon_to_place(48.866161, 2.312553)
PETIT_PALAIS = latlon_to_place(48.86604, 2.31453)
PONT_ALEXANDRE_III = latlon_to_place(48.863611, 2.313611)
# Terrasses des Tuileries, en surplomb du bord est de la place.
JEU_DE_PAUME = latlon_to_place(48.86583, 2.32389)
ORANGERIE = latlon_to_place(48.86378, 2.32253)
RIVOLI_FACADE_V = 160.0         # alignement des arcades de la rue de Rivoli
CHAMPS_ELYSEES_HALF_W = 35.0

# --- Date et lieu de la prise de vues --------------------------------------
# En 1925 la France applique l'heure d'été (UTC+1) du 4 avril au 4 octobre.
SHOOT_DATE = (1925, 6, 12)
SHOOT_LOCAL_TIME = 15.5   # 15 h 30
SHOOT_UTC_OFFSET = 1.0


def sun_direction(year: int, month: int, day: int, local_hour: float,
                  utc_offset: float, lat: float = LAT0, lon: float = LON0
                  ) -> tuple[float, float]:
    """Azimut (0° = nord, horaire) et hauteur du soleil, en degrés (algorithme NOAA)."""
    n = (367 * year - 7 * (year + (month + 9) // 12) // 4 + 275 * month // 9
         + day - 730530)  # jours depuis le 0 janvier 2000 à 0 h UT
    ut = local_hour - utc_offset
    d = n - 1.5 + ut / 24.0  # jours depuis J2000.0 (1er janvier 2000, 12 h TT)
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    ecl_lon = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.00000036 * d)
    ra = math.atan2(math.cos(eps) * math.sin(ecl_lon), math.cos(ecl_lon))
    dec = math.asin(math.sin(eps) * math.sin(ecl_lon))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    ha = math.radians(((gmst * 15 + lon) - math.degrees(ra) + 540) % 360 - 180)
    la = math.radians(lat)
    alt = math.asin(math.sin(la) * math.sin(dec)
                    + math.cos(la) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha) * math.cos(dec),
                    math.cos(la) * math.sin(dec)
                    - math.sin(la) * math.cos(dec) * math.cos(ha))
    return math.degrees(az) % 360, math.degrees(alt)
