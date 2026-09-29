"""Lecture des formats de scénario : Fountain, texte, PDF, Final Draft (FDX), DOCX, ODT.

Tout le traitement est fait en local ; aucune bibliothèque utilisée ici n'effectue d'accès réseau.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

from . import rules
from .model import Screenplay
from .structure import Line, build, classify

# À incrémenter quand l'analyse change : les versions stockées sont ré-analysées automatiquement.
PARSER_VERSION = 3

SUPPORTED = {
    ".fountain": "Fountain",
    ".spmd": "Fountain",
    ".txt": "Texte",
    ".fdx": "Final Draft",
    ".docx": "Word",
    ".odt": "OpenDocument",
    ".pdf": "PDF",
}

MAX_PDF_PAGES = 2000


class ParseError(Exception):
    pass


def detect_format(filename: str, data: bytes) -> str:
    name = filename.lower()
    for ext in SUPPORTED:
        if name.endswith(ext):
            return ext[1:]
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
            if "word/document.xml" in names:
                return "docx"
            if "content.xml" in names:
                return "odt"
        except zipfile.BadZipFile:
            pass
    head = data[:2000].lstrip()
    if head.startswith(b"<?xml") and b"<FinalDraft" in data[:5000]:
        return "fdx"
    return "txt"


def parse_file(filename: str, data: bytes) -> Screenplay:
    fmt = detect_format(filename, data)
    if fmt in ("fountain", "spmd"):
        return parse_fountain(decode_text(data))
    if fmt == "txt":
        return parse_text(decode_text(data))
    if fmt == "pdf":
        return parse_pdf(data)
    if fmt == "fdx":
        return parse_fdx(data)
    if fmt == "docx":
        return parse_docx(data)
    if fmt == "odt":
        return parse_odt(data)
    raise ParseError(f"Format non pris en charge : {filename}")


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16") if data[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("cp1252")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _expand(line: str) -> tuple[str, int]:
    line = line.replace("\t", "    ").rstrip()
    stripped = line.lstrip(" ")
    return stripped, len(line) - len(stripped)


# ---------------------------------------------------------------------------
# Fountain
# ---------------------------------------------------------------------------

_EMPHASIS_RE = re.compile(r"(\*{1,3}|_)(?=\S)(.+?)(?<=\S)\1")


def _strip_emphasis(s: str) -> str:
    prev = None
    while prev != s:
        prev, s = s, _EMPHASIS_RE.sub(r"\2", s)
    return s.replace("\\*", "*").replace("\\_", "_")


def parse_fountain(text: str) -> Screenplay:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)  # boneyard
    text = re.sub(r"\[\[.*?\]\]", "", text, flags=re.S)  # notes
    raw_lines = text.split("\n")

    title_page: dict = {}
    start = 0
    while start < len(raw_lines) and not raw_lines[start].strip():
        start += 1
    if start < len(raw_lines) and re.match(r"^[A-Za-z][A-Za-z ]{0,30}:", raw_lines[start]):
        key = None
        i = start
        while i < len(raw_lines) and raw_lines[i].strip():
            ln = raw_lines[i]
            m = re.match(r"^([A-Za-z][A-Za-z ]{0,30}):\s*(.*)$", ln)
            if m and not ln.startswith((" ", "\t")):
                key = m.group(1).strip().lower()
                title_page[key] = m.group(2).strip()
            elif key:
                title_page[key] = (title_page[key] + "\n" + ln.strip()).strip()
            i += 1
        start = i

    lines: list[Line] = []
    for raw in raw_lines[start:]:
        s, ind = _expand(raw)
        forced = None
        dual = False
        if s.startswith("!") and not s.startswith("!!"):
            forced, s = "action", s[1:]
        elif s.startswith(".") and not s.startswith(".."):
            forced, s = "heading", s[1:]
        elif s.startswith("@"):
            forced, s = "character", s[1:]
            dual = s.rstrip().endswith("^")
        elif s.startswith(">") and s.rstrip().endswith("<"):
            forced, s = "centered", s[1:-1]
        elif s.startswith(">"):
            forced, s = "transition", s[1:]
        elif s.startswith("~"):
            forced, s = "lyrics", s[1:]
        elif re.match(r"^={3,}\s*$", s):
            forced, s = "page_break", ""
        elif s.startswith("#"):
            forced, s = "section", s.lstrip("#")
        elif s.startswith("=") :
            forced, s = "synopsis", s[1:]
        s = _strip_emphasis(s.strip())
        lines.append(Line(text=s, indent=ind, forced=forced, dual=dual))
    elements = classify(lines, "fountain")
    return build(elements, "fountain", title_page)


# ---------------------------------------------------------------------------
# Texte brut / PDF
# ---------------------------------------------------------------------------

def _clean_page_lines(pages: list[list[str]]) -> list[str]:
    """Supprime entêtes/pieds de page répétés, numéros de page et marques (SUITE),
    puis recolle les pages (un paragraphe coupé par un saut de page reste entier)."""
    def key(s: str) -> str:
        return re.sub(r"\d+", "#", re.sub(r"\s+", " ", s.strip().lower()))

    n = len(pages)
    edge_counts: Counter = Counter()
    for page in pages:
        nb = [ln for ln in page if ln.strip()]
        for ln in set(nb[:2] + nb[-2:]):
            edge_counts[key(ln)] += 1

    def is_repeated(line: str) -> bool:
        k = key(line)
        c = edge_counts.get(k, 0)
        if not k.strip("# .-") or n < 2:
            return False
        st = line.strip()
        if rules.parse_heading(st)[0] or rules.is_transition(st):
            return False
        if rules.looks_like_character(st):
            return c >= max(3, 0.8 * n)
        if "#" in k:
            return c >= max(2, 0.3 * n)
        return c >= max(3, 0.5 * n)

    out: list[str] = []
    for page in pages:
        nb_idx = [i for i, ln in enumerate(page) if ln.strip()]
        edge = set(nb_idx[:2] + nb_idx[-2:])
        kept = []
        for i, ln in enumerate(page):
            st = ln.strip()
            if i in edge and (rules.PAGE_NUMBER_RE.match(st) or is_repeated(ln)):
                continue
            if st and rules.PAGE_ARTIFACT_RE.match(st):
                continue
            kept.append(ln)
        while kept and not kept[0].strip():
            kept.pop(0)
        while kept and not kept[-1].strip():
            kept.pop()
        if not kept:
            continue
        if out:
            prev = out[-1].rstrip()
            first = kept[0]
            same_indent = (len(prev) - len(prev.lstrip())) == (len(first) - len(first.lstrip()))
            # Paragraphe coupé par le saut de page : pas de ligne vide entre les deux morceaux
            cut_paragraph = same_indent and prev and prev[-1] not in ".!?…:»\")" and not rules.parse_heading(first)[0]
            # Nom de personnage en bas de page : la réplique continue sur la page suivante
            orphan_name = rules.looks_like_character(prev.strip()) and not rules.looks_like_character(first.strip())
            if not (cut_paragraph or orphan_name):
                out.append("")
        out.extend(kept)
    return out


def _text_lines_to_screenplay(raw_lines: list[str], source: str, warnings: list | None = None,
                              title_page: dict | None = None) -> Screenplay:
    lines = []
    for raw in raw_lines:
        s, ind = _expand(raw)
        lines.append(Line(text=s, indent=ind))
    elements = classify(lines, "text")
    return build(elements, source, title_page, warnings)


def parse_text(text: str) -> Screenplay:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\f" in text:
        pages = [p.split("\n") for p in text.split("\f")]
        raw_lines = _clean_page_lines(pages)
    else:
        raw_lines = [ln for ln in text.split("\n") if not rules.PAGE_ARTIFACT_RE.match(ln.strip()) or not ln.strip()]
    return _text_lines_to_screenplay(raw_lines, "text")


def parse_pdf(data: bytes) -> Screenplay:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ParseError("La bibliothèque pypdf est nécessaire pour lire les PDF.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            reader.decrypt("")
    except Exception as exc:
        raise ParseError(f"PDF illisible : {exc}") from exc
    warnings = []
    pages: list[list[str]] = []
    n = len(reader.pages)
    if n > MAX_PDF_PAGES:
        raise ParseError(f"PDF trop long ({n} pages).")
    for page in reader.pages:
        try:
            txt = page.extract_text(extraction_mode="layout")
        except Exception:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
        pages.append(_dedent_page(txt.split("\n")))
    total_chars = sum(len(ln.strip()) for p in pages for ln in p)
    if total_chars < 50 * max(1, n) * 0.2:
        warnings.append(
            "Très peu de texte extrait du PDF : il s'agit peut-être d'un scan (image). "
            "Utilisez un export texte, FDX ou Fountain pour une comparaison fiable."
        )
    title_page = {}
    if n > 3 and pages:
        first = [ln.strip() for ln in pages[0] if ln.strip()]
        if first and len(first) <= 20 and not any(rules.parse_heading(ln)[0] for ln in first):
            title_page = {"page de titre": "\n".join(first)}
            pages = pages[1:]
    raw_lines = _clean_page_lines(pages)
    return _text_lines_to_screenplay(raw_lines, "pdf", warnings, title_page)


def _dedent_page(lines: list[str]) -> list[str]:
    """Retire la marge commune d'une page (garde l'indentation relative)."""
    nb = [len(ln) - len(ln.lstrip(" ")) for ln in lines if ln.strip()]
    if not nb:
        return lines
    m = min(nb)
    return [ln[m:] if ln.strip() else "" for ln in lines]


# ---------------------------------------------------------------------------
# Final Draft (.fdx)
# ---------------------------------------------------------------------------

_FDX_TYPES = {
    "scene heading": "heading",
    "action": "action",
    "general": "action",
    "shot": "action",
    "character": "character",
    "dialogue": "dialogue",
    "parenthetical": "parenthetical",
    "transition": "transition",
    "lyrics": "lyrics",
    "new act": "section",
    "end of act": "section",
    "cast list": None,
}


def _safe_xml(data: bytes) -> ET.Element:
    if b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data[:65536]:
        raise ParseError("Document XML refusé (DTD/entités non autorisées).")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ParseError(f"XML invalide : {exc}") from exc


def parse_fdx(data: bytes) -> Screenplay:
    root = _safe_xml(data)
    content = root.find("Content")
    if content is None:
        raise ParseError("Fichier Final Draft sans contenu.")
    lines: list[Line] = []

    def para_text(p: ET.Element) -> str:
        return "".join((t.text or "") for t in p.iter("Text")).replace("\t", " ")

    def add_para(p: ET.Element, dual: bool = False):
        ptype = (p.get("Type") or "Action").strip().lower()
        style = _FDX_TYPES.get(ptype, "action")
        if style is None:
            return
        txt = para_text(p).strip()
        if not txt:
            return
        lines.append(Line(text=txt, style=style, scene_number=p.get("Number") or "", dual=dual))

    for child in content:
        if child.tag == "Paragraph":
            dd = child.find("DualDialogue")
            if dd is not None:
                for k, p in enumerate(dd.iter("Paragraph")):
                    add_para(p, dual=True)
            else:
                add_para(child)
    title_page = {}
    tp = root.find("TitlePage")
    if tp is not None:
        txt = [("".join((t.text or "") for t in p.iter("Text"))).strip() for p in tp.iter("Paragraph")]
        txt = [t for t in txt if t]
        if txt:
            title_page = {"page de titre": "\n".join(txt)}
    elements = classify(lines, "paragraph")
    return build(elements, "fdx", title_page)


# ---------------------------------------------------------------------------
# Word (.docx)
# ---------------------------------------------------------------------------

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_STYLE_HINTS = [
    (("parenthetical", "parenthes", "indication de jeu", "didascalie de dialogue", "didascalie dialogue",
      "didascalie de jeu", "parenthet"), "parenthetical"),
    (("scene heading", "slugline", "slug line", "en-tete", "entete", "en tete", "intitule", "heading de scene",
      "titre de sequence", "sequence", "tete de sequence"), "heading"),
    (("character", "personnage", "nom du perso", "nom de personnage", "role"), "character"),
    (("dialogue", "dialog", "replique", "texte du dialogue"), "dialogue"),
    (("transition", "enchainement"), "transition"),
    (("action", "description", "didascalie", "general", "shot", "plan"), "action"),
]


def _style_hint(name: str) -> str | None:
    n = rules.strip_accents(name or "").lower().strip()
    if not n or n in ("normal", "default paragraph font", "standard", "default"):
        return None
    for keys, kind in _STYLE_HINTS:
        if any(k in n for k in keys):
            return kind
    return None


def _twips(v: str | None) -> int | None:
    try:
        return int(float(v)) if v is not None else None
    except ValueError:
        return None


def parse_docx(data: bytes) -> Screenplay:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        doc = _safe_xml(z.read("word/document.xml"))
        styles_xml = _safe_xml(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ParseError(f"Document Word invalide : {exc}") from exc

    styles: dict[str, dict] = {}
    if styles_xml is not None:
        for st in styles_xml.iter(W + "style"):
            sid = st.get(W + "styleId")
            name_el = st.find(W + "name")
            based = st.find(W + "basedOn")
            ind = st.find(f"{W}pPr/{W}ind")
            caps = st.find(f"{W}rPr/{W}caps")
            styles[sid] = {
                "name": name_el.get(W + "val") if name_el is not None else sid,
                "based": based.get(W + "val") if based is not None else None,
                "indent": _twips(ind.get(W + "left") or ind.get(W + "start")) if ind is not None else None,
                "caps": caps is not None and caps.get(W + "val", "true") not in ("0", "false"),
            }

    def style_attr(sid, attr):
        seen = set()
        while sid and sid in styles and sid not in seen:
            seen.add(sid)
            v = styles[sid].get(attr)
            if v not in (None, False):
                return v
            sid = styles[sid].get("based")
        return None

    paras = []
    body = doc.find(W + "body")
    if body is None:
        raise ParseError("Document Word vide.")
    for p in body.iter(W + "p"):
        ppr = p.find(W + "pPr")
        sid = None
        indent = None
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            sid = ps.get(W + "val") if ps is not None else None
            ind = ppr.find(W + "ind")
            if ind is not None:
                indent = _twips(ind.get(W + "left") or ind.get(W + "start"))
        if indent is None:
            indent = style_attr(sid, "indent") or 0
        pcaps = bool(style_attr(sid, "caps"))
        buf = []
        for node in p.iter():
            tag = node.tag
            if tag == W + "r":
                rpr = node.find(W + "rPr")
                caps = pcaps
                if rpr is not None:
                    c = rpr.find(W + "caps")
                    if c is not None:
                        caps = c.get(W + "val", "true") not in ("0", "false")
                for sub in node:
                    if sub.tag == W + "t":
                        buf.append((sub.text or "").upper() if caps else (sub.text or ""))
                    elif sub.tag == W + "tab":
                        buf.append(" ")
                    elif sub.tag in (W + "br", W + "cr"):
                        buf.append("\n")
        # Les textes supprimés en suivi des modifications (w:delText) sont ignorés : on lit l'état final.
        text = "".join(buf)
        name = styles.get(sid, {}).get("name", "") if sid else ""
        paras.append((text, indent, _style_hint(name) if name else None))

    kinds = Counter(k for _, _, k in paras if k)
    use_styles = kinds.get("heading", 0) + kinds.get("character", 0) >= 2 and len(kinds) >= 2
    lines = []
    for text, indent, hint in paras:
        for i, part in enumerate(text.split("\n") if not (use_styles and hint) else [text.replace("\n", " ")]):
            lines.append(Line(text=part.strip(), indent=(indent or 0) // 144,
                              style=hint if use_styles and hint and part.strip() else None))
    return build(classify(lines, "paragraph"), "docx")


# ---------------------------------------------------------------------------
# OpenDocument (.odt)
# ---------------------------------------------------------------------------

NS_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
NS_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
NS_FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"


def _length_to_chars(v: str | None) -> int:
    if not v:
        return 0
    m = re.match(r"^(-?[\d.]+)(cm|mm|in|pt)?$", v.strip())
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2) or "cm"
    inches = {"cm": val / 2.54, "mm": val / 25.4, "in": val, "pt": val / 72}[unit]
    return int(round(inches * 10))


def parse_odt(data: bytes) -> Screenplay:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        content = _safe_xml(z.read("content.xml"))
        styles_root = _safe_xml(z.read("styles.xml")) if "styles.xml" in z.namelist() else None
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ParseError(f"Document ODT invalide : {exc}") from exc

    styles: dict[str, dict] = {}
    for root in [r for r in (styles_root, content) if r is not None]:
        for st in root.iter(NS_STYLE + "style"):
            name = st.get(NS_STYLE + "name")
            pp = st.find(NS_STYLE + "paragraph-properties")
            styles[name] = {
                "display": st.get(NS_STYLE + "display-name") or name,
                "parent": st.get(NS_STYLE + "parent-style-name"),
                "indent": _length_to_chars(pp.get(NS_FO + "margin-left")) if pp is not None else None,
            }

    def resolve(name, attr):
        seen = set()
        while name and name in styles and name not in seen:
            seen.add(name)
            v = styles[name].get(attr)
            if attr == "display":
                hint = _style_hint(v or "")
                if hint:
                    return hint
            elif v:
                return v
            name = styles[name].get("parent")
        return None

    def text_of(el) -> str:
        parts = [el.text or ""]
        for ch in el:
            if ch.tag == NS_TEXT + "s":
                parts.append(" " * int(ch.get(NS_TEXT + "c", "1")))
            elif ch.tag == NS_TEXT + "tab":
                parts.append(" ")
            elif ch.tag == NS_TEXT + "line-break":
                parts.append("\n")
            elif ch.tag in (NS_TEXT + "note", NS_OFFICE + "annotation", NS_TEXT + "tracked-changes"):
                pass
            else:
                parts.append(text_of(ch))
            parts.append(ch.tail or "")
        return "".join(parts)

    body = content.find(f"{NS_OFFICE}body/{NS_OFFICE}text")
    if body is None:
        raise ParseError("Document ODT vide.")
    paras = []

    def walk(el):
        for ch in el:
            if ch.tag == NS_TEXT + "tracked-changes":
                continue
            if ch.tag in (NS_TEXT + "p", NS_TEXT + "h"):
                sname = ch.get(NS_TEXT + "style-name")
                paras.append((text_of(ch), resolve(sname, "indent") or 0, resolve(sname, "display")))
            else:
                walk(ch)

    walk(body)
    kinds = Counter(k for _, _, k in paras if k)
    use_styles = kinds.get("heading", 0) + kinds.get("character", 0) >= 2 and len(kinds) >= 2
    lines = []
    for text, indent, hint in paras:
        for part in text.split("\n") if not (use_styles and hint) else [text.replace("\n", " ")]:
            lines.append(Line(text=part.strip(), indent=indent,
                              style=hint if use_styles and hint and part.strip() else None))
    return build(classify(lines, "paragraph"), "odt")
