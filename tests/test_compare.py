import time

from app.compare.engine import compare
from app.compare.text import Options, word_diff
from app.screenplay.parsers import parse_fountain
from tests.synth import make_script, mutate


def changed(result):
    return [(s["label_b"], u) for s in result["scenes"] for u in s["units"] if u["status"] != "unchanged" or u.get("moved")]


def test_identical(v1):
    r = compare(v1, v1)
    assert r["summary"]["identical"]
    assert r["summary"]["change_ratio"] == 0


def test_fixture_changes(v1, v2):
    r = compare(v1, v2)
    s = r["summary"]
    assert s["scenes"]["added"] == 1 and s["scenes"]["moved"] == 1 and s["scenes"]["deleted"] == 0
    moved = [x for x in r["scenes"] if x["moved"]]
    # deux séquences voisines interverties : l'une des deux est signalée comme déplacée
    assert moved[0]["heading_b"] in ("EXT. PLAGE - AUBE", "EXT. PHARE - NUIT")
    units = {u["text"]: u for _, u in changed(r)}
    assert units["Pas comme ça."]["reassigned"] and units["Pas comme ça."]["character_a"] == "MARIE"
    assert units["Alors qui l'a éteint ?"]["status"] == "deleted"
    marie = units["Pas du tout. Le phare a clignoté toute la nuit."]
    assert marie["status"] == "modified"
    assert ["-", " vraiment", ""] in marie["diff"] and ["+", "", " du tout"] in marie["diff"]
    chars = {c["name"]: c for c in r["characters"]}
    assert chars["JULIEN"]["status"] == "new"


def test_word_diff_reconstructs_texts():
    a = "Bonjour, je m’appelle Paul.\nEt toi ?"
    b = "Bonsoir, je m'appelle Paul. Et toi, qui es-tu ?"
    segs, d, i = word_diff(a, b, Options())
    assert "".join(x[1] for x in segs) == a
    assert "".join(x[2] for x in segs) == b
    assert d == 1 and i >= 3


def test_typography_and_whitespace_ignored():
    a = parse_fountain("INT. A - JOUR\n\nMARIE\nC’est « beau »…\n")
    b = parse_fountain("INT. A - JOUR\n\nMARIE\nC'est \"beau\"...\n")
    assert compare(a, b)["summary"]["identical"]
    assert not compare(a, b, Options(normalize_typo=False))["summary"]["identical"]
    c = parse_fountain("INT. A - JOUR\n\nLe   ciel\nest bleu.\n")
    d = parse_fountain("INT. A - JOUR\n\nLe ciel est bleu.\n")
    assert compare(c, d)["summary"]["identical"]


def test_minor_and_options():
    a = parse_fountain("INT. A - JOUR\n\nMARIE\nBonjour, Paul.\n")
    b = parse_fountain("INT. A - JOUR\n\nMARIE\nbonjour Paul !\n")
    r = compare(a, b)
    u = changed(r)[0][1]
    assert u["status"] == "modified" and u["minor"]
    assert compare(a, b, Options(ignore_case=True, ignore_punct=True))["summary"]["identical"]


def test_heading_change_and_extension():
    a = parse_fountain("INT. CUISINE - JOUR\n\nPAUL\nSalut.\n\nIl sort par la porte de derrière.\n")
    b = parse_fountain("INT. CUISINE - NUIT\n\nPAUL (O.S.)\nSalut.\n\nIl sort par la porte de derrière.\n")
    r = compare(a, b)
    sc = r["scenes"][0]
    assert sc["heading_changed"] and sc["status"] == "modified"
    u = sc["units"][0]
    assert u["ext_changed"] and u["extension_a"] == "" and u["extension"] == "O.S."


def test_move_within_and_across_scenes():
    a = parse_fountain(
        "INT. A - JOUR\n\nPremière action assez longue pour être reconnue.\n\n"
        "Deuxième action tout aussi longue que la première.\n\nMARIE\nUne réplique qui va changer de séquence.\n\n"
        "EXT. B - NUIT\n\nAction de la séquence B bien distincte des autres.\n")
    b = parse_fountain(
        "INT. A - JOUR\n\nDeuxième action tout aussi longue que la première.\n\n"
        "Première action assez longue pour être reconnue.\n\n"
        "EXT. B - NUIT\n\nAction de la séquence B bien distincte des autres.\n\nMARIE\n"
        "Une réplique qui va changer de séquence.\n")
    r = compare(a, b)
    units = [u for _, u in changed(r)]
    assert any(u.get("moved") for u in units)
    added = [u for u in units if u["status"] == "added"]
    assert added and added[0]["moved_from"] == "1"
    assert r["summary"]["units"]["dialogue"]["moved"] == 1


def test_rename_detected():
    a = parse_fountain("INT. A - JOUR\n\nJEAN\nPremière réplique de Jean.\n\nJEAN\nSeconde réplique de Jean ici.\n")
    b = parse_fountain("INT. A - JOUR\n\nJACQUES\nPremière réplique de Jean.\n\nJACQUES\nSeconde réplique de Jean ici.\n")
    r = compare(a, b)
    assert r["renames"] == [{"from": "JEAN", "to": "JACQUES", "lines": 2}]


def test_long_script_accuracy_and_speed():
    a = make_script(1, 200)
    b, log = mutate(a, 3)
    t = time.perf_counter()
    r = compare(a, b)
    assert time.perf_counter() - t < 10
    sc = r["summary"]["scenes"]
    assert sc["deleted"] == len(log["deleted_scenes"])
    assert sc["added"] == log["added_scenes"]
    assert sc["moved"] == len(log["moved_scenes"])
    mods = r["summary"]["units"]["dialogue"]["modified"] + r["summary"]["units"]["action"]["modified"]
    assert mods == log["modified_units"]
