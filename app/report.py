"""Exports d'une comparaison : rapport HTML autonome (imprimable en PDF) et CSV."""
from __future__ import annotations

import csv
import io
import time
from html import escape

STATUS_FR = {
    "unchanged": "Inchangé",
    "modified": "Modifié",
    "added": "Ajouté",
    "deleted": "Supprimé",
}
KIND_FR = {"dialogue": "Réplique", "action": "Action", "transition": "Transition"}

CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d232b;margin:32px auto;max-width:1000px;
padding:0 16px;line-height:1.45}
h1{font-size:1.6rem;margin:0 0 4px}h2{margin-top:2rem;border-bottom:2px solid #dde3ea;padding-bottom:4px}
.meta{color:#5b6673;font-size:.9rem}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:8px 0}
th,td{border:1px solid #dde3ea;padding:4px 8px;text-align:left;vertical-align:top}th{background:#f3f6f9}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.scene{border:1px solid #dde3ea;border-radius:8px;margin:14px 0;page-break-inside:avoid;overflow:hidden}
.scene>header{background:#f3f6f9;padding:6px 10px;font-weight:600;font-family:"Courier Prime",Courier,monospace}
.scene>header .tag{font-family:system-ui,sans-serif;font-weight:500}
.unit{padding:6px 10px;border-top:1px solid #eef1f4;white-space:pre-wrap;font-family:"Courier Prime",Courier,monospace;
font-size:.92rem}
.unit .who{font-weight:700}
.tag{display:inline-block;font-size:.72rem;padding:1px 6px;border-radius:10px;margin-left:6px;background:#e7ebf0;
color:#333}
.t-added{background:#d8f5e0;color:#11622b}.t-deleted{background:#fde0e0;color:#8c1c1c}
.t-modified{background:#fff1cc;color:#7a5600}.t-moved{background:#e3e3ff;color:#3b3b9a}
.u-added{background:#f1fbf4}.u-deleted{background:#fdf3f3}
ins{background:#c7f0d3;text-decoration:none}del{background:#f9c9c9;color:#7a1414}
.u-deleted .body{text-decoration:line-through;color:#8c1c1c}
@media print{body{margin:0}.scene{break-inside:avoid}}
"""


def _segs(segs: list) -> str:
    out = []
    for op, a, b in segs:
        if op == "=":
            out.append(escape(b))
        elif op == "-":
            out.append(f"<del>{escape(a)}</del>")
        else:
            out.append(f"<ins>{escape(b)}</ins>")
    return "".join(out)


def _unit_html(u: dict) -> str:
    st = u["status"]
    tags = []
    if st != "unchanged":
        tags.append(f'<span class="tag t-{st}">{STATUS_FR[st]}</span>')
    if u.get("moved") or u.get("moved_from") or u.get("moved_to"):
        where = ""
        if u.get("moved_from"):
            where = f" depuis séq. {escape(str(u['moved_from']))}"
        elif u.get("moved_to"):
            where = f" vers séq. {escape(str(u['moved_to']))}"
        tags.append(f'<span class="tag t-moved">Déplacé{where}</span>')
    if u.get("minor"):
        tags.append('<span class="tag">Ponctuation / casse</span>')
    who = ""
    if u["kind"] == "dialogue":
        name = escape(u.get("character", ""))
        if u.get("character_a") and u.get("character_a") != u.get("character"):
            name = f"<del>{escape(u['character_a'])}</del> → <ins>{name}</ins>"
        ext = u.get("extension") or ""
        if u.get("ext_changed"):
            ext = f"{u.get('extension_a') or '—'} → {ext or '—'}"
        who = f'<div class="who">{name}{" (" + escape(ext) + ")" if ext else ""}</div>'
    body = _segs(u["diff"]) if u.get("diff") else escape(u["text"])
    label = KIND_FR.get(u["kind"], u["kind"])
    return (f'<div class="unit u-{st}"><div class="meta">{label}{"".join(tags)}</div>{who}'
            f'<div class="body">{body}</div></div>')


def render_html(result: dict, title_a: str, title_b: str, project: str = "", include_unchanged: bool = False) -> str:
    s = result["summary"]
    sc = s["scenes"]
    parts = [
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Comparaison – {escape(title_a)} → {escape(title_b)}</title><style>{CSS}</style></head><body>",
        f"<h1>{escape(project) + ' — ' if project else ''}Comparaison de versions</h1>",
        f"<div class='meta'><b>A :</b> {escape(title_a)} &nbsp;→&nbsp; <b>B :</b> {escape(title_b)}"
        f"<br>Rapport généré le {time.strftime('%d/%m/%Y à %H:%M')}</div>",
        "<h2>Synthèse</h2><table><tr><th></th><th>Version A</th><th>Version B</th></tr>",
        f"<tr><td>Séquences</td><td class='n'>{sc['a']}</td><td class='n'>{sc['b']}</td></tr>",
        f"<tr><td>Mots</td><td class='n'>{s['words']['a']}</td><td class='n'>{s['words']['b']}</td></tr>",
        f"<tr><td>Pages (estimation)</td><td class='n'>{s['pages']['a']}</td><td class='n'>{s['pages']['b']}</td></tr>",
        "</table><table><tr><th>Séquences</th><th>Nombre</th></tr>",
    ]
    for k, lab in (("modified", "Modifiées"), ("added", "Ajoutées"), ("deleted", "Supprimées"),
                   ("moved", "Déplacées"), ("heading_changed", "Entête modifié"), ("unchanged", "Inchangées")):
        parts.append(f"<tr><td>{lab}</td><td class='n'>{sc[k]}</td></tr>")
    parts.append("</table><table><tr><th></th><th>Modifiées</th><th>Ajoutées</th><th>Supprimées</th>"
                 "<th>Déplacées</th><th>Réattribuées</th></tr>")
    for k, lab in (("dialogue", "Répliques"), ("action", "Actions"), ("transition", "Transitions")):
        u = s["units"][k]
        parts.append(f"<tr><td>{lab}</td><td class='n'>{u['modified']}</td><td class='n'>{u['added']}</td>"
                     f"<td class='n'>{u['deleted']}</td><td class='n'>{u['moved']}</td>"
                     f"<td class='n'>{u['reassigned'] if k == 'dialogue' else ''}</td></tr>")
    parts.append(f"</table><p>Mots ajoutés : <b>{s['words']['added']}</b> — mots supprimés : "
                 f"<b>{s['words']['deleted']}</b> — taux de changement : <b>{s['change_ratio'] * 100:.1f} %</b></p>")
    if result.get("renames"):
        parts.append("<h2>Renommages probables</h2><ul>")
        for r in result["renames"]:
            parts.append(f"<li>{escape(r['from'])} → {escape(r['to'])} ({r['lines']} répliques)</li>")
        parts.append("</ul>")
    parts.append("<h2>Personnages</h2><table><tr><th>Personnage</th><th>Statut</th><th>Répliques A</th>"
                 "<th>Répliques B</th><th>Mots A</th><th>Mots B</th><th>+ mots</th><th>− mots</th></tr>")
    st_fr = {"common": "", "new": "Nouveau", "removed": "Disparu"}
    for c in result["characters"]:
        parts.append(
            f"<tr><td>{escape(c['name'])}</td><td>{st_fr[c['status']]}</td><td class='n'>{c['a']['lines']}</td>"
            f"<td class='n'>{c['b']['lines']}</td><td class='n'>{c['a']['words']}</td>"
            f"<td class='n'>{c['b']['words']}</td><td class='n'>{c['words_add']}</td>"
            f"<td class='n'>{c['words_del']}</td></tr>")
    parts.append("</table><h2>Détail par séquence</h2>")
    for scene in result["scenes"]:
        if scene["status"] == "unchanged" and not scene["moved"] and not include_unchanged:
            continue
        head = escape(scene["heading_b"] if scene["heading_b"] is not None else scene["heading_a"] or "")
        if scene.get("heading_diff"):
            head = _segs(scene["heading_diff"])
        if scene["prologue"]:
            head = "Ouverture (avant la première séquence)"
        la, lb = scene["label_a"], scene["label_b"]
        num = f"{la or '—'} → {lb or '—'}" if la != lb else str(lb)
        tags = f'<span class="tag t-{scene["status"]}">{STATUS_FR[scene["status"]]}</span>'
        if scene["moved"]:
            tags += '<span class="tag t-moved">Déplacée</span>'
        parts.append(f'<section class="scene"><header>Séq. {escape(num)} — {head}{tags}</header>')
        for u in scene["units"]:
            if u["status"] == "unchanged" and not u.get("moved") and not include_unchanged:
                continue
            parts.append(_unit_html(u))
        parts.append("</section>")
    parts.append("</body></html>")
    return "".join(parts)


def render_csv(result: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Séq. A", "Séq. B", "Entête", "Statut séquence", "Type", "Personnage A", "Personnage B",
                "Statut", "Déplacement", "Mineur", "Mots supprimés", "Mots ajoutés", "Texte A", "Texte B"])
    for s in result["scenes"]:
        for u in s["units"]:
            if u["status"] == "unchanged" and not u.get("moved"):
                continue
            move = ""
            if u.get("moved"):
                move = "dans la séquence"
            elif u.get("moved_from"):
                move = f"depuis séq. {u['moved_from']}"
            elif u.get("moved_to"):
                move = f"vers séq. {u['moved_to']}"
            ta = u.get("text_a", u["text"]) if u["status"] != "added" else ""
            tb = u["text"] if u["status"] != "deleted" else ""
            if u["status"] == "added" and u.get("text_a"):
                ta = u["text_a"]
            w.writerow([
                s["label_a"] or "", s["label_b"] or "", s["heading_b"] or s["heading_a"] or "",
                STATUS_FR[s["status"]], KIND_FR.get(u["kind"], u["kind"]),
                u.get("character_a", u.get("character", "")) if u["status"] != "added" else "",
                u.get("character", "") if u["status"] != "deleted" else "",
                STATUS_FR[u["status"]], move, "oui" if u.get("minor") else "",
                u.get("words_del", 0), u.get("words_add", 0), ta, tb,
            ])
    return "﻿" + buf.getvalue()  # BOM pour ouverture correcte dans Excel
