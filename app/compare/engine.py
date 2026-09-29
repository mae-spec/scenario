"""Moteur de comparaison entre deux versions d'un scénario.

Étapes :
1. alignement des séquences (ordre conservé, par programmation dynamique sur une
   mesure de ressemblance entête + contenu), puis détection des séquences déplacées ;
2. pour chaque paire de séquences, alignement des unités (actions, répliques,
   transitions) avec détection des répliques réattribuées et des déplacements ;
3. différences mot à mot dans les unités modifiées ;
4. détection des unités déplacées d'une séquence à une autre ;
5. synthèse : compteurs, personnages, renommages probables.
"""
from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ..screenplay import rules
from ..screenplay.model import Scene, Screenplay, Unit
from ..screenplay.stats import count_words, screenplay_stats
from .text import LOOSE, Options, comparable, ratio, word_diff, word_keys

STOPWORDS = set(
    """le la les l un une des de du d et à a au aux en dans sur sous par pour pas ne n se s il elle ils elles
    on je j tu vous nous me m te t lui leur y que qu qui quoi ce c cet cette ces son sa ses mon ma mes ton ta
    tes est sont a ont être avoir fait plus mais ou où donc car si the a an of to in on at and or is are it
    he she they we you i his her their its be was with for as by this that not""".split()
)

SCENE_MATCH_MIN = 0.33
SCENE_CONTENT_MIN = 0.12
SCENE_MOVE_MIN = 0.5
SCENE_MOVE_CONTENT_MIN = 0.35
UNIT_MOVE_MIN = 0.75
CROSS_MOVE_MIN = 0.85


@dataclass
class PUnit:
    unit: Unit
    words: list
    cmp: tuple
    loose: tuple
    group: str

    @property
    def char(self) -> str:
        return self.unit.character


@dataclass
class PScene:
    scene: Scene
    index: int
    label: str
    hnorm: str
    hwords: set
    units: list
    uni: set = field(default_factory=set)
    bi: set = field(default_factory=set)
    digest: str = ""


def _group(kind: str) -> str:
    return kind if kind in ("dialogue", "transition") else "action"


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def _prepare(sp: Screenplay, opts: Options) -> list[PScene]:
    out = []
    ordinal = 0
    for idx, sc in enumerate(sp.scenes):
        if not sc.prologue:
            ordinal += 1
        label = "Ouverture" if sc.prologue else (sc.number or str(ordinal))
        units = []
        all_words: list[str] = []
        h = hashlib.sha1()
        h.update(repr(comparable(sc.heading, opts)).encode())
        for u in sc.units:
            wk = word_keys(u.text)
            cmp = comparable(u.text, opts)
            units.append(PUnit(u, wk, cmp, comparable(u.text, LOOSE), _group(u.kind)))
            if u.kind == "dialogue":
                all_words.append("@" + u.character.casefold())
            all_words.extend(wk)
            h.update(repr((u.kind, u.character, u.extension, cmp)).encode())
        hn = rules.normalize_heading(sc.heading)
        ps = PScene(sc, idx, label, hn, set(hn.split()), units)
        content = [w for w in all_words if w not in STOPWORDS]
        ps.uni = set(content)
        ps.bi = {a + " " + b for a, b in zip(all_words, all_words[1:])}
        ps.digest = h.hexdigest()
        out.append(ps)
    return out


# ---------------------------------------------------------------------------
# Alignement générique
# ---------------------------------------------------------------------------

def _monotone(scores: list[list[float]]) -> list[tuple[int, int]]:
    """Appariement croissant maximisant la somme des scores (> 0)."""
    n = len(scores)
    m = len(scores[0]) if n else 0
    if not n or not m:
        return []
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        row, prev, srow = dp[i], dp[i - 1], scores[i - 1]
        for j in range(1, m + 1):
            best = prev[j] if prev[j] >= row[j - 1] else row[j - 1]
            s = srow[j - 1]
            if s > 0:
                cand = prev[j - 1] + s
                if cand > best:
                    best = cand
            row[j] = best
    pairs = []
    i, j = n, m
    while i > 0 and j > 0:
        s = scores[i - 1][j - 1]
        if s > 0 and dp[i][j] == dp[i - 1][j - 1] + s:
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] >= dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return pairs


def _anchors(ka: list, kb: list) -> list[tuple[int, int]]:
    """Ancres « patience » : éléments identiques et uniques des deux côtés, dans l'ordre (plus longue
    sous-suite croissante). Elles découpent le problème en petits blocs indépendants."""
    ca, cb = Counter(ka), Counter(kb)
    pos_b = {k: j for j, k in enumerate(kb) if cb[k] == 1}
    seq = [(i, pos_b[k]) for i, k in enumerate(ka) if ca[k] == 1 and k in pos_b]
    if not seq:
        return []
    tails: list[int] = []  # indices dans seq
    prev = [-1] * len(seq)
    for idx, (_, j) in enumerate(seq):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if seq[tails[mid]][1] < j:
                lo = mid + 1
            else:
                hi = mid
        prev[idx] = tails[lo - 1] if lo else -1
        if lo == len(tails):
            tails.append(idx)
        else:
            tails[lo] = idx
    out = []
    k = tails[-1]
    while k != -1:
        out.append(seq[k])
        k = prev[k]
    return out[::-1]


def _align(a: list, b: list, key, score, move_score) -> tuple[list, list]:
    """Aligne deux suites. Retourne (paires_dans_l_ordre, paires_déplacées)."""
    n, m = len(a), len(b)
    ka = [key(x) for x in a]
    kb = [key(y) for y in b]
    pairs: list[tuple[int, int]] = []

    def block(i0, i1, j0, j1):
        # Préfixe / suffixe identiques, puis programmation dynamique sur le reste
        while i0 < i1 and j0 < j1 and ka[i0] == kb[j0]:
            pairs.append((i0, j0))
            i0 += 1
            j0 += 1
        tail = []
        while i0 < i1 and j0 < j1 and ka[i1 - 1] == kb[j1 - 1]:
            i1 -= 1
            j1 -= 1
            tail.append((i1, j1))
        if i0 < i1 and j0 < j1:
            scores = [[score(a[i], b[j]) for j in range(j0, j1)] for i in range(i0, i1)]
            pairs.extend((i + i0, j + j0) for i, j in _monotone(scores))
        pairs.extend(reversed(tail))

    pi, pj = 0, 0
    for ai, bj in _anchors(ka, kb):
        block(pi, ai, pj, bj)
        pairs.append((ai, bj))
        pi, pj = ai + 1, bj + 1
    block(pi, n, pj, m)
    pairs.sort()

    used_a = {i for i, _ in pairs}
    used_b = {j for _, j in pairs}
    free_a = [i for i in range(n) if i not in used_a]
    free_b = [j for j in range(m) if j not in used_b]
    moved = []
    if free_a and free_b and len(free_a) * len(free_b) <= 250_000:
        cands = []
        for i in free_a:
            for j in free_b:
                s = move_score(a[i], b[j])
                if s > 0:
                    cands.append((s, i, j))
        cands.sort(key=lambda t: (-t[0], t[1], t[2]))
        ta, tb = set(), set()
        for s, i, j in cands:
            if i in ta or j in tb:
                continue
            ta.add(i)
            tb.add(j)
            moved.append((i, j))
    return pairs, moved


def _merge_order(n: int, m: int, pairs: list, moved: list) -> list[tuple]:
    """Ordre d'affichage : ordre de B, éléments supprimés insérés à leur place dans A."""
    a2b = {i: j for i, j in pairs}
    b2a = {j: i for i, j in pairs}
    mv_b2a = {j: i for i, j in moved}
    moved_a = {i for i, _ in moved}
    head, after = [], defaultdict(list)
    last_anchor = None
    for i in range(n):
        if i in a2b:
            last_anchor = a2b[i]
        elif i not in moved_a:
            (after[last_anchor] if last_anchor is not None else head).append(i)
    out = [(i, None, False) for i in head]
    for j in range(m):
        if j in b2a:
            out.append((b2a[j], j, False))
        elif j in mv_b2a:
            out.append((mv_b2a[j], j, True))
        else:
            out.append((None, j, False))
        out.extend((i, None, False) for i in after.get(j, []))
    return out


# ---------------------------------------------------------------------------
# Séquences
# ---------------------------------------------------------------------------

def _scene_content_sim(a: PScene, b: PScene) -> float:
    if not a.uni and not b.uni and not a.bi and not b.bi:
        return 1.0
    return 0.5 * _jaccard(a.uni, b.uni) + 0.5 * _jaccard(a.bi, b.bi)


def _scene_heading_sim(a: PScene, b: PScene) -> float:
    return 1.0 if a.hnorm == b.hnorm else _jaccard(a.hwords, b.hwords)


def _scene_score(a: PScene, b: PScene) -> float:
    if a.scene.prologue or b.scene.prologue:
        return 1.0 if a.scene.prologue and b.scene.prologue else 0.0
    if a.digest == b.digest:
        return 3.0
    c = _scene_content_sim(a, b)
    s = 0.75 * c + 0.25 * _scene_heading_sim(a, b)
    return s if s >= SCENE_MATCH_MIN and c >= SCENE_CONTENT_MIN else 0.0


def _scene_move_score(a: PScene, b: PScene) -> float:
    if a.scene.prologue or b.scene.prologue:
        return 0.0
    if a.digest == b.digest:
        return 3.0
    c = _scene_content_sim(a, b)
    s = 0.75 * c + 0.25 * _scene_heading_sim(a, b)
    return s if s >= SCENE_MOVE_MIN and c >= SCENE_MOVE_CONTENT_MIN else 0.0


# ---------------------------------------------------------------------------
# Unités
# ---------------------------------------------------------------------------

def _unit_key(u: PUnit) -> tuple:
    return (u.group, u.cmp, u.char, u.unit.extension)


def _unit_score(a: PUnit, b: PUnit) -> float:
    if a.group != b.group:
        return 0.0
    if a.cmp == b.cmp and a.char == b.char:
        return 3.0
    if a.group == "transition":
        return 0.1 + ratio(a.words, b.words)
    if a.group == "dialogue":
        if a.char == b.char:
            r = ratio(a.words, b.words, 0.3)
            return r + 0.2 if r >= 0.3 else 0.0
        r = ratio(a.words, b.words, 0.6)
        return r if r >= 0.6 else 0.0
    r = ratio(a.words, b.words, 0.35)
    return r if r >= 0.35 else 0.0


def _unit_move_score(a: PUnit, b: PUnit) -> float:
    if a.group != b.group:
        return 0.0
    if a.cmp == b.cmp:
        return 3.0
    r = ratio(a.words, b.words, UNIT_MOVE_MIN)
    return r if r >= UNIT_MOVE_MIN else 0.0


def _unit_payload(pu: PUnit, side: str) -> dict:
    u = pu.unit
    d = {"kind": u.kind, "text": u.text}
    if u.kind == "dialogue":
        d.update(character=u.character, extension=u.extension)
        if u.dual:
            d["dual"] = True
    return d


def _compare_units(ua: PUnit | None, ub: PUnit | None, opts: Options, a_idx, b_idx, moved: bool) -> dict:
    if ub is None:
        u = ua.unit
        rec = {"status": "deleted", "a": a_idx, "b": None, **_unit_payload(ua, "a"),
               "words_del": count_words(u.text), "words_add": 0}
        return rec
    if ua is None:
        u = ub.unit
        return {"status": "added", "a": None, "b": b_idx, **_unit_payload(ub, "b"),
                "words_del": 0, "words_add": count_words(u.text)}
    same_text = ua.cmp == ub.cmp
    reassigned = ua.unit.kind == "dialogue" and ua.char != ub.char
    ext_changed = ua.unit.kind == "dialogue" and ua.unit.extension != ub.unit.extension
    rec = {"a": a_idx, "b": b_idx, **_unit_payload(ub, "b")}
    if moved:
        rec["moved"] = True
    if same_text and not reassigned and not ext_changed:
        rec.update(status="unchanged", words_del=0, words_add=0)
        return rec
    rec["status"] = "modified"
    rec["text_a"] = ua.unit.text
    if reassigned:
        rec["reassigned"] = True
        rec["character_a"] = ua.char
    if ext_changed:
        rec["ext_changed"] = True
        rec["extension_a"] = ua.unit.extension
    if not same_text:
        segs, d, a = word_diff(ua.unit.text, ub.unit.text, opts)
        rec["diff"] = segs
        rec["words_del"], rec["words_add"] = d, a
        if ua.loose == ub.loose:
            rec["minor"] = True
    else:
        rec["words_del"] = rec["words_add"] = 0
    return rec


def _scene_record(pa: PScene | None, pb: PScene | None, opts: Options, moved: bool) -> dict:
    rec: dict = {
        "a": pa.index if pa else None,
        "b": pb.index if pb else None,
        "label_a": pa.label if pa else None,
        "label_b": pb.label if pb else None,
        "heading_a": pa.scene.heading if pa else None,
        "heading_b": pb.scene.heading if pb else None,
        "prologue": bool((pa or pb).scene.prologue),
        "moved": moved,
    }
    units: list[dict] = []
    if pa is None:
        rec["status"] = "added"
        units = [_compare_units(None, u, opts, None, k, False) for k, u in enumerate(pb.units)]
    elif pb is None:
        rec["status"] = "deleted"
        units = [_compare_units(u, None, opts, k, None, False) for k, u in enumerate(pa.units)]
    else:
        if comparable(pa.scene.heading, opts) != comparable(pb.scene.heading, opts):
            rec["heading_changed"] = True
            rec["heading_diff"] = word_diff(pa.scene.heading, pb.scene.heading, opts)[0]
            if comparable(pa.scene.heading, LOOSE) == comparable(pb.scene.heading, LOOSE):
                rec["heading_minor"] = True
        if pa.scene.number and pb.scene.number and pa.scene.number != pb.scene.number:
            rec["renumbered"] = True
        if pa.digest == pb.digest:
            units = [_compare_units(u, pb.units[k], opts, k, k, False) for k, u in enumerate(pa.units)]
        else:
            pairs, mv = _align(pa.units, pb.units, _unit_key, _unit_score, _unit_move_score)
            for i, j, is_moved in _merge_order(len(pa.units), len(pb.units), pairs, mv):
                units.append(_compare_units(pa.units[i] if i is not None else None,
                                            pb.units[j] if j is not None else None, opts, i, j, is_moved))
        changed = rec.get("heading_changed") or any(u["status"] != "unchanged" or u.get("moved") for u in units)
        rec["status"] = "modified" if changed else "unchanged"
        rec["similarity"] = round(min(1.0, _scene_content_sim(pa, pb)), 3)
    rec["units"] = units
    ca = {u.char for u in pa.units if u.unit.kind == "dialogue"} if pa else set()
    cb = {u.char for u in pb.units if u.unit.kind == "dialogue"} if pb else set()
    rec["characters"] = sorted(ca | cb)
    if pa and pb:
        rec["chars_added"] = sorted(cb - ca)
        rec["chars_removed"] = sorted(ca - cb)
    return rec


def _cross_scene_moves(scenes: list[dict], opts: Options) -> None:
    added, deleted = [], []
    for s in scenes:
        for u in s["units"]:
            if u["status"] == "added":
                added.append((s, u))
            elif u["status"] == "deleted":
                deleted.append((s, u))
    if not added or not deleted:
        return
    by_key: dict = defaultdict(list)
    for s, u in deleted:
        by_key[(u["kind"], comparable(u["text"], opts))].append((s, u))
    rest_added = []
    for s, u in added:
        lst = by_key.get((u["kind"], comparable(u["text"], opts)))
        if lst:
            sd, ud = lst.pop(0)
            _link_move(sd, ud, s, u, opts)
        else:
            rest_added.append((s, u))
    rest_deleted = [(s, u) for s, u in deleted if "moved_to" not in u]
    if not rest_added or not rest_deleted or len(rest_added) * len(rest_deleted) > 40_000:
        return
    cache = {}
    cands = []
    for ai, (s, u) in enumerate(rest_added):
        wa = cache.setdefault(id(u), word_keys(u["text"]))
        if len(wa) < 4:
            continue
        for di, (sd, ud) in enumerate(rest_deleted):
            if ud["kind"] != u["kind"]:
                continue
            wd = cache.setdefault(id(ud), word_keys(ud["text"]))
            r = ratio(wd, wa, CROSS_MOVE_MIN)
            if r >= CROSS_MOVE_MIN:
                cands.append((r, ai, di))
    cands.sort(key=lambda t: -t[0])
    ua_used, ud_used = set(), set()
    for r, ai, di in cands:
        if ai in ua_used or di in ud_used:
            continue
        ua_used.add(ai)
        ud_used.add(di)
        sd, ud = rest_deleted[di]
        s, u = rest_added[ai]
        _link_move(sd, ud, s, u, opts)


def _link_move(sd: dict, ud: dict, sa: dict, ua: dict, opts: Options) -> None:
    ud["moved_to"] = sa["label_b"]
    ua["moved_from"] = sd["label_a"]
    if comparable(ud["text"], opts) != comparable(ua["text"], opts):
        segs, d, a = word_diff(ud["text"], ua["text"], opts)
        ua["diff"] = segs
        ua["text_a"] = ud["text"]
        ua["move_words_del"], ua["move_words_add"] = d, a
    if ud.get("character") and ud.get("character") != ua.get("character"):
        ua["character_a"] = ud["character"]


# ---------------------------------------------------------------------------
# Synthèse
# ---------------------------------------------------------------------------

def _summarize(scenes: list[dict], stats_a: dict, stats_b: dict) -> tuple[dict, list, list]:
    sc = defaultdict(int)
    units = {k: defaultdict(int) for k in ("dialogue", "action", "transition")}
    words_add = words_del = 0
    per_char = defaultdict(lambda: defaultdict(int))
    reassign = defaultdict(int)
    for s in scenes:
        if not s["prologue"]:
            sc[s["status"]] += 1
            if s["moved"]:
                sc["moved"] += 1
            if s.get("heading_changed"):
                sc["heading_changed"] += 1
            if s.get("renumbered"):
                sc["renumbered"] += 1
        for u in s["units"]:
            k = units[_group(u["kind"])]
            st = u["status"]
            if st == "added" and "moved_from" in u:
                k["moved"] += 1
                wd, wa = u.get("move_words_del", 0), u.get("move_words_add", 0)
            elif st == "deleted" and "moved_to" in u:
                continue
            else:
                k[st] += 1
                if u.get("moved"):
                    k["moved"] += 1
                wd, wa = u.get("words_del", 0), u.get("words_add", 0)
            if u.get("reassigned"):
                k["reassigned"] += 1
            if u.get("minor"):
                k["minor"] += 1
            words_add += wa
            words_del += wd
            if u["kind"] == "dialogue":
                cb = u.get("character")
                ca = u.get("character_a", cb)
                if st == "added" and "moved_from" not in u:
                    per_char[cb]["lines_added"] += 1
                    per_char[cb]["words_add"] += wa
                elif st == "deleted":
                    per_char[cb]["lines_deleted"] += 1
                    per_char[cb]["words_del"] += wd
                elif st == "modified" or "moved_from" in u:
                    if ca != cb:
                        reassign[(ca, cb)] += 1
                        per_char[ca]["lines_deleted"] += 1
                        per_char[ca]["words_del"] += count_words(u.get("text_a", u["text"]))
                        per_char[cb]["lines_added"] += 1
                        per_char[cb]["words_add"] += count_words(u["text"])
                    elif wa or wd or u.get("ext_changed"):
                        per_char[cb]["lines_modified"] += 1
                        per_char[cb]["words_add"] += wa
                        per_char[cb]["words_del"] += wd

    ca = {c["name"]: c for c in stats_a["characters"]}
    cb = {c["name"]: c for c in stats_b["characters"]}
    only_a = set(ca) - set(cb)
    only_b = set(cb) - set(ca)
    renames = []
    for (x, y), n in sorted(reassign.items(), key=lambda t: -t[1]):
        if x in only_a and y in only_b and n >= max(1, 0.5 * ca[x]["lines"]):
            renames.append({"from": x, "to": y, "lines": n})
    renamed_from = {r["from"]: r["to"] for r in renames}
    renamed_to = {r["to"]: r["from"] for r in renames}
    characters = []
    empty = {"lines": 0, "words": 0, "scenes": 0}
    for name in sorted(set(ca) | set(cb)):
        a, b = ca.get(name, empty), cb.get(name, empty)
        status = "common"
        if name in only_a:
            status = "removed"
        elif name in only_b:
            status = "new"
        pc = per_char.get(name, {})
        characters.append({
            "name": name,
            "status": status,
            "renamed_to": renamed_from.get(name),
            "renamed_from": renamed_to.get(name),
            "a": {"lines": a["lines"], "words": a["words"], "scenes": a["scenes"]},
            "b": {"lines": b["lines"], "words": b["words"], "scenes": b["scenes"]},
            "lines_added": pc.get("lines_added", 0),
            "lines_deleted": pc.get("lines_deleted", 0),
            "lines_modified": pc.get("lines_modified", 0),
            "words_add": pc.get("words_add", 0),
            "words_del": pc.get("words_del", 0),
        })
    characters.sort(key=lambda c: (-(c["b"]["lines"] + c["a"]["lines"]), c["name"]))
    total = stats_a["words"] + stats_b["words"]
    summary = {
        "scenes": {
            "a": stats_a["scenes"], "b": stats_b["scenes"],
            **{k: sc.get(k, 0) for k in ("unchanged", "modified", "added", "deleted", "moved",
                                        "heading_changed", "renumbered")},
        },
        "units": {k: {s: v.get(s, 0) for s in ("unchanged", "modified", "added", "deleted", "moved",
                                               "reassigned", "minor")} for k, v in units.items()},
        "words": {"a": stats_a["words"], "b": stats_b["words"], "added": words_add, "deleted": words_del},
        "pages": {"a": stats_a["pages"], "b": stats_b["pages"]},
        "change_ratio": round((words_add + words_del) / total, 4) if total else 0.0,
        "identical": all(s["status"] == "unchanged" and not s["moved"] for s in scenes),
    }
    return summary, characters, renames


def compare(sp_a: Screenplay, sp_b: Screenplay, opts: Options | None = None) -> dict:
    opts = opts or Options()
    pa = _prepare(sp_a, opts)
    pb = _prepare(sp_b, opts)
    pairs, moved = _align(pa, pb, lambda x: x.digest, _scene_score, _scene_move_score)
    scenes = []
    for i, j, is_moved in _merge_order(len(pa), len(pb), pairs, moved):
        rec = _scene_record(pa[i] if i is not None else None, pb[j] if j is not None else None, opts, is_moved)
        rec["id"] = len(scenes)
        scenes.append(rec)
    _cross_scene_moves(scenes, opts)
    stats_a, stats_b = screenplay_stats(sp_a), screenplay_stats(sp_b)
    summary, characters, renames = _summarize(scenes, stats_a, stats_b)
    return {
        "options": {"ignore_case": opts.ignore_case, "ignore_punct": opts.ignore_punct,
                    "normalize_typo": opts.normalize_typo},
        "summary": summary,
        "characters": characters,
        "renames": renames,
        "scenes": scenes,
        "stats": {"a": stats_a, "b": stats_b},
    }
