"""Génération de longs scénarios synthétiques pour tester performances et précision."""
import random

from app.screenplay.model import Scene, Screenplay, Unit

WORDS = ("maison phare mer nuit lumière porte fenêtre route voiture silence regard main café lettre clé "
         "orage vent sable bateau ville église rue marché ombre secret enfant père mère frère sœur ami "
         "chemin horloge livre photo carte train quai valise pluie soleil matin soir heure minute").split()
VERBS = "regarde prend ouvre ferme court marche attend cherche trouve dit pense sourit pleure crie entre sort".split()
NAMES = ["MARIE", "PAUL", "JULIEN", "LÉA", "LE MAIRE", "ANNE", "THOMAS", "SOPHIE", "MARC", "CLAIRE"]
PLACES = ["CUISINE", "PHARE", "PLAGE", "BUREAU DU MAIRE", "GRENIER", "PORT", "ÉGLISE", "GARE", "RUE", "SALON"]


def sentence(rng, n=None):
    n = n or rng.randint(5, 16)
    w = [rng.choice(WORDS) if i % 3 else rng.choice(VERBS) for i in range(n)]
    return (" ".join(w)).capitalize() + rng.choice([".", " !", " ?", "..."])


def make_script(seed=1, n_scenes=150):
    rng = random.Random(seed)
    sp = Screenplay(source_format="synth")
    for i in range(n_scenes):
        heading = f"{rng.choice(['INT.', 'EXT.'])} {rng.choice(PLACES)} - {rng.choice(['JOUR', 'NUIT', 'SOIR'])}"
        sc = Scene(heading=heading, number=str(i + 1))
        for _ in range(rng.randint(3, 25)):
            if rng.random() < 0.6:
                t = " ".join(sentence(rng) for _ in range(rng.randint(1, 3)))
                sc.units.append(Unit(kind="dialogue", text=t, character=rng.choice(NAMES),
                                     parts=[{"type": "line", "text": t}]))
            else:
                sc.units.append(Unit(kind="action", text=" ".join(sentence(rng) for _ in range(rng.randint(1, 4)))))
        sp.scenes.append(sc)
    return sp


def mutate(sp, seed=2):
    """Applique des modifications connues ; retourne (nouveau_scénario, journal)."""
    import copy
    rng = random.Random(seed)
    new = copy.deepcopy(sp)
    log = {"deleted_scenes": [], "moved_scenes": [], "added_scenes": 0, "modified_units": 0,
           "reassigned": 0, "deleted_units": 0, "added_units": 0}
    for _ in range(3):
        k = rng.randrange(len(new.scenes))
        log["deleted_scenes"].append(new.scenes[k].heading)
        del new.scenes[k]
    for _ in range(2):
        k = rng.randrange(len(new.scenes))
        sc = new.scenes.pop(k)
        new.scenes.insert(rng.randrange(len(new.scenes)), sc)
        log["moved_scenes"].append(sc.heading)
    for _ in range(2):
        sc = Scene(heading="INT. NOUVEAU DÉCOR - NUIT", units=[Unit(kind="action", text=sentence(rng, 12))])
        new.scenes.insert(rng.randrange(len(new.scenes)), sc)
        log["added_scenes"] += 1
    for sc in rng.sample(new.scenes, 30):
        if not sc.units or not sc.number:
            continue
        u = rng.choice(sc.units)
        words = u.text.split()
        if len(words) > 6:
            words[rng.randrange(len(words))] = "MODIFIÉ"
            u.text = " ".join(words)
            if u.parts:
                u.parts = [{"type": "line", "text": u.text}]
            log["modified_units"] += 1
    return new, log
