"""Statistiques d'une version (personnages, décors, estimation du nombre de pages)."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from . import rules
from .model import Screenplay

WORD_RE = re.compile(r"\w+(?:['’]\w+)*", re.U)

# Estimation au format standard (Courier 12) : ~56 lignes par page,
# ~60 caractères par ligne d'action, ~35 par ligne de dialogue.
LINES_PER_PAGE = 56


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def _wrapped(text: str, width: int) -> int:
    return sum(max(1, math.ceil(len(part) / width)) for part in (text or "").split("\n"))


def estimate_lines(sp: Screenplay) -> int:
    total = 0
    for scene in sp.scenes:
        if not scene.prologue:
            total += 2
        for u in scene.units:
            if u.kind == "dialogue":
                total += 1 + sum(_wrapped(p["text"], 25 if p["type"] == "paren" else 35) for p in u.parts) + 1
            elif u.kind == "transition":
                total += 2
            else:
                total += _wrapped(u.text, 60) + 1
    return total


def screenplay_stats(sp: Screenplay) -> dict:
    chars: dict[str, dict] = defaultdict(lambda: {"lines": 0, "words": 0, "scenes": set()})
    locations = set()
    int_ext = defaultdict(int)
    words_dialogue = words_action = n_dialogue = n_action = 0
    for idx, scene in enumerate(sp.scenes):
        if not scene.prologue:
            parts = rules.heading_parts(scene.heading)
            if parts["location"]:
                locations.add(parts["location"])
            int_ext[parts["int_ext"] or "?"] += 1
        for u in scene.units:
            w = count_words(u.text)
            if u.kind == "dialogue":
                n_dialogue += 1
                words_dialogue += w
                c = chars[u.character]
                c["lines"] += 1
                c["words"] += w
                c["scenes"].add(idx)
            else:
                n_action += 1
                words_action += w
    lines = estimate_lines(sp)
    return {
        "scenes": sum(1 for s in sp.scenes if not s.prologue),
        "dialogues": n_dialogue,
        "actions": n_action,
        "words": words_dialogue + words_action,
        "words_dialogue": words_dialogue,
        "words_action": words_action,
        "pages": round(lines / LINES_PER_PAGE, 1),
        "locations": len(locations),
        "int_ext": dict(int_ext),
        "characters": sorted(
            (
                {"name": name, "lines": c["lines"], "words": c["words"], "scenes": len(c["scenes"])}
                for name, c in chars.items()
            ),
            key=lambda c: (-c["lines"], c["name"]),
        ),
    }
