"""Export d'un scénario analysé au format Fountain (utile pour vérifier l'analyse)."""
from __future__ import annotations

from .model import Screenplay


def to_fountain(sp: Screenplay) -> str:
    out: list[str] = []
    for k, v in sp.title_page.items():
        lines = str(v).split("\n")
        out.append(f"{k.title()}: {lines[0]}")
        out.extend("    " + ln for ln in lines[1:])
    if sp.title_page:
        out.append("")
    for scene in sp.scenes:
        for sec in scene.sections:
            out += [f"# {sec}", ""]
        if not scene.prologue:
            num = f" #{scene.number}#" if scene.number else ""
            out += [f".{scene.heading}{num}" if not scene.heading.upper().startswith(("INT", "EXT", "I/E", "EST"))
                    else f"{scene.heading}{num}", ""]
        for u in scene.units:
            if u.kind == "dialogue":
                ext = f" ({u.extension})" if u.extension else ""
                out.append(f"@{u.character}{ext}{' ^' if u.dual else ''}")
                for p in u.parts:
                    out.append(p["text"])
            elif u.kind == "transition":
                out.append(f"> {u.text}")
            else:
                first = u.text.split("\n")[0]
                forced = u.text[:1] in "!.@>~#=[" or (first.isupper() and len(first) < 50)
                out.append("!" + u.text if forced else u.text)
            out.append("")
    return "\n".join(out).rstrip() + "\n"
