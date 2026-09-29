"""Découpage en mots, normalisation et différences mot à mot."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from ..screenplay.rules import normalize_typography

# Un mot (avec apostrophes internes : « aujourd'hui », « l'homme ») ou un signe isolé.
TOKEN_RE = re.compile(r"\w+(?:['’]\w+)*|\.{2,}|[^\w\s]", re.U)
WORD_RE = re.compile(r"\w", re.U)
WORD_ONLY_RE = re.compile(r"\w+(?:['’]\w+)*", re.U)


@dataclass(frozen=True)
class Options:
    ignore_case: bool = False
    ignore_punct: bool = False
    normalize_typo: bool = True

    @property
    def key(self) -> tuple:
        return (self.ignore_case, self.ignore_punct, self.normalize_typo)


LOOSE = Options(ignore_case=True, ignore_punct=True, normalize_typo=True)


@lru_cache(maxsize=200_000)
def _norm(tok: str, typo: bool, case: bool) -> str:
    if typo:
        tok = normalize_typography(tok)
    if case:
        tok = tok.casefold()
    return tok


def norm_token(tok: str, opts: Options) -> str:
    return _norm(tok, opts.normalize_typo, opts.ignore_case)


def chunks(text: str, opts: Options) -> tuple[list[str], list[str]]:
    """Découpe ``text`` en morceaux affichables et en clés de comparaison.

    Chaque morceau contient l'espace qui le précède, pour que la concaténation
    des morceaux redonne exactement le texte d'origine. Si la ponctuation est
    ignorée, elle est rattachée au mot précédent et exclue de la clé.
    """
    text = text or ""
    shown: list[str] = []
    keys: list[str] = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        tok = m.group(0)
        piece = text[pos:m.end()]
        pos = m.end()
        is_word = bool(WORD_RE.match(tok))
        if opts.ignore_punct and not is_word:
            if shown:
                shown[-1] += piece
            else:
                shown.append(piece)
                keys.append("")
            continue
        shown.append(piece)
        keys.append(norm_token(tok, opts))
    if pos < len(text):
        if shown:
            shown[-1] += text[pos:]
        else:
            shown.append(text[pos:])
            keys.append("")
    if opts.ignore_punct and keys and keys[0] == "" and len(keys) > 1:
        # morceau de ponctuation initial : le fusionner avec le mot suivant
        shown[1] = shown[0] + shown[1]
        shown.pop(0)
        keys.pop(0)
    return shown, keys


def comparable(text: str, opts: Options) -> tuple:
    return tuple(k for k in chunks(text, opts)[1] if k)


def word_keys(text: str) -> list[str]:
    """Mots normalisés (sans ponctuation ni casse) pour mesurer la ressemblance."""
    return [_norm(t, True, True) for t in WORD_ONLY_RE.findall(text or "")]


def ratio(a: list[str], b: list[str], floor: float = 0.0) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
        return 0.0
    return sm.ratio()


def word_diff(a: str, b: str, opts: Options) -> tuple[list, int, int]:
    """Retourne (segments, mots_supprimés, mots_ajoutés).

    Segments : liste de [op, texte_A, texte_B] avec op ∈ {"=", "-", "+"}.
    """
    sa, ka = chunks(a, opts)
    sb, kb = chunks(b, opts)
    segs: list[list] = []
    deleted = inserted = 0

    def push(op, ta, tb):
        if segs and segs[-1][0] == op:
            segs[-1][1] += ta
            segs[-1][2] += tb
        else:
            segs.append([op, ta, tb])

    sm = SequenceMatcher(None, ka, kb, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push("=", "".join(sa[i1:i2]), "".join(sb[j1:j2]))
            continue
        if i2 > i1:
            ta = "".join(sa[i1:i2])
            deleted += sum(1 for k in ka[i1:i2] if k and WORD_RE.match(k))
            push("-", ta, "")
        if j2 > j1:
            tb = "".join(sb[j1:j2])
            inserted += sum(1 for k in kb[j1:j2] if k and WORD_RE.match(k))
            push("+", "", tb)
    return segs, deleted, inserted
