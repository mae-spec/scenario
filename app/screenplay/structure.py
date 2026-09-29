"""Classification ligne à ligne et regroupement en séquences / unités.

Trois modes :
- ``fountain`` : syntaxe Fountain (éléments forcés, règles strictes sur les lignes vides) ;
- ``text``     : texte brut ou extrait d'un PDF (lignes coupées, indentation éventuelle) ;
- ``paragraph``: un paragraphe par entrée (DOCX / ODT sans styles de scénario).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from . import rules
from .model import Element, Scene, Screenplay, Unit


@dataclass
class Line:
    text: str
    indent: int | None = None
    style: str | None = None  # type imposé par un style (DOCX/ODT/FDX)
    forced: str | None = None  # type forcé (Fountain)
    scene_number: str = ""
    dual: bool = False

    @property
    def blank(self) -> bool:
        return not self.text.strip() and self.style is None and self.forced is None


_INLINE_DIALOGUE_RE = re.compile(
    r"^(?P<name>[" + rules.UPPER_LETTERS + r"][" + rules.UPPER_LETTERS + r"0-9 .'’\-]{1,30}?)"
    r"\s*(?P<ext>\([^)]*\))?\s*:\s+(?P<text>\S.*)$"
)


def _indent_margin(lines: list[Line]) -> int | None:
    """Marge des actions si l'indentation est significative, sinon None."""
    indents = [ln.indent for ln in lines if not ln.blank and ln.indent is not None]
    if len(indents) < 12:
        return None
    heading_ind = [ln.indent for ln in lines if ln.indent is not None and rules.parse_heading(ln.text)[0]]
    if heading_ind:
        margin = Counter(heading_ind).most_common(1)[0][0]
    else:
        margin = sorted(indents)[max(0, len(indents) // 20)]
    deep = sum(1 for i in indents if i >= margin + 8)
    return margin if deep / len(indents) >= 0.12 else None


def classify(lines: list[Line], mode: str) -> list[Element]:
    margin = _indent_margin(lines) if mode != "fountain" else None
    join = "\n" if mode == "fountain" else " "
    inline_dialogue = False
    if mode != "fountain":
        hits = {ln.text.strip() for ln in lines if ln.style is None and _INLINE_DIALOGUE_RE.match(ln.text.strip())
                and rules.looks_like_character(_INLINE_DIALOGUE_RE.match(ln.text.strip()).group("name"))}
        inline_dialogue = len(hits) >= 3

    out: list[Element] = []
    in_dialogue = False
    speech_paras = 0
    paren_open = False
    prev_blank = True

    def append(kind: str, text: str, **kw):
        text = text.strip()
        if not text and kind not in ("page_break",):
            return
        # Regroupe les lignes consécutives d'un même bloc (modes ligne)
        if (
            mode != "paragraph"
            and out
            and kind in ("action", "dialogue", "parenthetical")
            and out[-1].type == kind
            and not prev_blank
        ):
            out[-1].text += join + text
            return
        out.append(Element(kind, text, **kw))

    def next_nonblank(idx: int) -> Line | None:
        for j in range(idx + 1, len(lines)):
            if mode != "paragraph":
                return lines[j]
            if not lines[j].blank:
                return lines[j]
        return None

    for idx, ln in enumerate(lines):
        if ln.blank:
            if mode != "paragraph":
                in_dialogue = False
                paren_open = False
            prev_blank = True
            continue
        raw = ln.text
        t = rules.REVISION_MARK_RE.sub("", raw.strip())
        kind = ln.style or ln.forced

        if kind:
            if kind == "heading":
                ok, h, num = rules.parse_heading(t)
                out.append(Element("heading", h if ok else t, scene_number=ln.scene_number or num))
                in_dialogue = False
            elif kind == "character":
                out.append(Element("character", t, dual=ln.dual))
                in_dialogue, speech_paras = True, 0
            elif kind in ("dialogue", "parenthetical"):
                if mode == "paragraph" or ln.style:
                    out.append(Element(kind, t))
                else:
                    append(kind, t)
                in_dialogue = True
            else:
                append(kind, t) if kind == "action" else out.append(Element(kind, t))
                in_dialogue = False
            prev_blank = False
            continue

        # --- Poursuite d'une réplique ---
        if in_dialogue:
            ends = False
            if rules.parse_heading(t)[0]:
                ends = True
            elif margin is not None and ln.indent is not None and ln.indent < margin + 4:
                ends = True
            elif mode == "paragraph" and speech_paras >= 1 and not t.startswith("("):
                ends = True
            elif inline_dialogue and (m := _INLINE_DIALOGUE_RE.match(t)) and rules.looks_like_character(m.group("name")):
                ends = True
            if not ends:
                if paren_open and out and out[-1].type == "parenthetical":
                    out[-1].text += " " + t
                    paren_open = not t.rstrip().endswith(")")
                elif t.startswith("("):
                    out.append(Element("parenthetical", t))
                    paren_open = ")" not in t
                else:
                    if mode == "paragraph":
                        out.append(Element("dialogue", t))
                    else:
                        append("dialogue", t)
                    speech_paras += 1
                prev_blank = False
                continue
            in_dialogue = False
            paren_open = False

        # --- Classification d'une ligne libre ---
        ok, h, num = rules.parse_heading(t)
        if ok:
            out.append(Element("heading", h, scene_number=ln.scene_number or num))
        elif rules.is_transition(t) and (prev_blank or mode == "paragraph"):
            out.append(Element("transition", t))
        elif (
            inline_dialogue
            and (m := _INLINE_DIALOGUE_RE.match(t))
            and rules.looks_like_character(m.group("name"))
        ):
            out.append(Element("character", m.group("name") + (" " + m.group("ext") if m.group("ext") else "")))
            out.append(Element("dialogue", m.group("text")))
            in_dialogue, speech_paras = True, 1
        elif _is_character(ln, t, idx, lines, mode, margin, prev_blank, next_nonblank(idx)):
            out.append(Element("character", t, dual=t.endswith("^")))
            in_dialogue, speech_paras, paren_open = True, 0, False
        else:
            if mode == "paragraph":
                out.append(Element("action", t))
            else:
                append("action", t)
        prev_blank = False
    return out


def _is_character(ln, t, idx, lines, mode, margin, prev_blank, nxt) -> bool:
    if not rules.looks_like_character(t):
        return False
    if nxt is None or nxt.blank:
        return False
    nt = nxt.text.strip()
    if rules.parse_heading(nt)[0] or rules.is_transition(nt):
        return False
    if nxt.style and nxt.style not in ("dialogue", "parenthetical"):
        return False
    if mode == "fountain" and not prev_blank:
        return False
    if margin is not None and ln.indent is not None:
        if ln.indent < margin + 8:
            return False
        if nxt.indent is not None and nxt.indent < margin + 4:
            return False
    if mode == "paragraph" and rules.looks_like_character(nt) and not nt.startswith("("):
        return False
    return True


def build(elements: list[Element], source_format: str, title_page: dict | None = None,
          warnings: list | None = None) -> Screenplay:
    sp = Screenplay(source_format=source_format, title_page=title_page or {}, warnings=list(warnings or []))
    scene = Scene(heading="", prologue=True)
    dlg: Unit | None = None

    def close_dialogue():
        nonlocal dlg
        if dlg is None:
            return
        if not dlg.parts:
            # Un « personnage » sans réplique était en fait une ligne d'action
            scene.units.append(Unit(kind="action", text=dlg.text))
        else:
            dlg.text = "\n".join(p["text"] for p in dlg.parts)
            prev = scene.units[-1] if scene.units else None
            if (
                prev is not None and prev.kind == "dialogue" and prev.character == dlg.character
                and getattr(dlg, "_continuation", False)
            ):
                prev.parts.extend(dlg.parts)
                prev.text = "\n".join(p["text"] for p in prev.parts)
            else:
                scene.units.append(dlg)
        dlg = None

    for el in elements:
        text = el.text.strip()
        if el.type == "heading":
            close_dialogue()
            if scene.units or not scene.prologue or scene.sections:
                sp.scenes.append(scene)
            scene = Scene(heading=text, number=el.scene_number)
        elif el.type == "character":
            close_dialogue()
            name, ext, dual, cont = rules.split_character(text)
            dlg = Unit(kind="dialogue", text=text, character=name, extension=ext, dual=dual or el.dual)
            dlg._continuation = cont  # type: ignore[attr-defined]
        elif el.type in ("dialogue", "parenthetical"):
            if dlg is None:
                scene.units.append(Unit(kind="action", text=text))
            else:
                ptype = "paren" if el.type == "parenthetical" else "line"
                if ptype == "line" and dlg.parts and dlg.parts[-1]["type"] == "line":
                    dlg.parts[-1]["text"] += "\n" + text
                else:
                    dlg.parts.append({"type": ptype, "text": text})
        else:
            close_dialogue()
            if el.type in ("action", "centered", "lyrics"):
                if text:
                    scene.units.append(Unit(kind="action", text=text))
            elif el.type == "transition":
                scene.units.append(Unit(kind="transition", text=text))
            elif el.type == "section":
                scene.sections.append(text)
    close_dialogue()
    if scene.units or not scene.prologue or scene.sections:
        sp.scenes.append(scene)
    for s in sp.scenes:
        for u in s.units:
            if hasattr(u, "_continuation"):
                delattr(u, "_continuation")
    if not any(not s.prologue for s in sp.scenes):
        sp.warnings.append(
            "Aucun entête de séquence (INT./EXT.) détecté : le document est traité comme une seule séquence."
        )
    return sp
