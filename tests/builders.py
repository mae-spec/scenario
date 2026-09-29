"""Génère des fichiers FDX / DOCX / ODT / PDF / TXT à partir d'un scénario analysé (pour les tests)."""
from __future__ import annotations

import io
import textwrap
import zipfile
from xml.sax.saxutils import escape

from app.screenplay.model import Screenplay


def elements(sp: Screenplay):
    """Suite (type, texte, numéro) au format « logiciel de scénario »."""
    for sc in sp.scenes:
        if not sc.prologue:
            yield "Scene Heading", sc.heading, sc.number
        for u in sc.units:
            if u.kind == "dialogue":
                yield "Character", u.character + (f" ({u.extension})" if u.extension else ""), ""
                for p in u.parts:
                    yield ("Parenthetical" if p["type"] == "paren" else "Dialogue"), p["text"].replace("\n", " "), ""
            elif u.kind == "transition":
                yield "Transition", u.text, ""
            else:
                yield "Action", u.text.replace("\n", " "), ""


def to_fdx(sp: Screenplay) -> bytes:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no" ?>', '<FinalDraft DocumentType="Script" Version="5">',
           "<Content>"]
    for typ, text, num in elements(sp):
        n = f' Number="{num}"' if num else ""
        out.append(f'<Paragraph Type="{typ}"{n}><Text>{escape(text)}</Text></Paragraph>')
    out += ["</Content>", "</FinalDraft>"]
    return "\n".join(out).encode("utf-8")


_DOCX_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
_DOCX_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

# (styleId, nom affiché FR, retrait en twips)
DOCX_STYLES = {
    "Scene Heading": ("Sequence", "Séquence", 0),
    "Action": ("Didascalie", "Didascalie", 0),
    "Character": ("Personnage", "Personnage", 3168),
    "Dialogue": ("Dialogue", "Dialogue", 1440),
    "Parenthetical": ("Parenthese", "Parenthèse", 2160),
    "Transition": ("Transition", "Transition", 5760),
}


def to_docx(sp: Screenplay, with_styles: bool = True, blank_paragraphs: bool = False) -> bytes:
    styles = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}>',
              '<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>']
    if with_styles:
        for sid, name, ind in DOCX_STYLES.values():
            styles.append(f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
                          f'<w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="{ind}"/></w:pPr></w:style>')
    styles.append("</w:styles>")
    body = []
    prev = None
    for typ, text, _ in elements(sp):
        sid, _, ind = DOCX_STYLES[typ]
        if blank_paragraphs and prev and typ in ("Scene Heading", "Action", "Character", "Transition"):
            body.append("<w:p/>")
        if with_styles:
            ppr = f'<w:pPr><w:pStyle w:val="{sid}"/></w:pPr>'
        else:
            ppr = f'<w:pPr><w:ind w:left="{ind}"/></w:pPr>'
        # un texte supprimé en suivi des modifications ne doit pas être lu
        extra = '<w:del w:id="1" w:author="x"><w:r><w:delText>SUPPRIMÉ</w:delText></w:r></w:del>' if typ == "Action" else ""
        body.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>{extra}</w:p>')
        prev = typ
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>'
           + "".join(body) + "</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", _DOCX_CT)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", "".join(styles))
    return buf.getvalue()


def to_odt(sp: Screenplay) -> bytes:
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"')
    names = {"Scene Heading": "Scene_20_Heading", "Action": "Action", "Character": "Character",
             "Dialogue": "Dialogue", "Parenthetical": "Parenthetical", "Transition": "Transition"}
    styles = [f'<?xml version="1.0" encoding="UTF-8"?><office:document-styles {ns}><office:styles>']
    for disp, name in names.items():
        styles.append(f'<style:style style:name="{name}" style:display-name="{disp}" style:family="paragraph"/>')
    styles.append("</office:styles></office:document-styles>")
    body = []
    for k, (typ, text, _) in enumerate(elements(sp)):
        # style automatique dérivé (comme LibreOffice le fait souvent)
        body.append(f'<text:p text:style-name="P{k}">{escape(text)}</text:p>')
    auto = "".join(f'<style:style style:name="P{k}" style:family="paragraph" '
                   f'style:parent-style-name="{names[typ]}"/>' for k, (typ, _, _) in enumerate(elements(sp)))
    content = (f'<?xml version="1.0" encoding="UTF-8"?><office:document-content {ns}>'
               f"<office:automatic-styles>{auto}</office:automatic-styles><office:body><office:text>"
               + "".join(body) + "</office:text></office:body></office:document-content>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", content)
        z.writestr("styles.xml", "".join(styles))
    return buf.getvalue()


# --- Texte mis en page (TXT et PDF) ------------------------------------------------

LAYOUT = {  # (retrait en caractères, largeur)
    "Scene Heading": (0, 60),
    "Action": (0, 60),
    "Character": (22, 38),
    "Dialogue": (10, 35),
    "Parenthetical": (16, 25),
    "Transition": (45, 15),
}


def layout_lines(sp: Screenplay, numbered: bool = True) -> list[str]:
    lines: list[str] = []
    prev = None
    for typ, text, num in elements(sp):
        ind, width = LAYOUT[typ]
        if prev is not None and not (typ in ("Dialogue", "Parenthetical") and prev in ("Character", "Dialogue",
                                                                                           "Parenthetical")):
            lines.append("")
        if typ == "Scene Heading" and numbered and num:
            text = f"{num}  {text}"
        for part in textwrap.wrap(text, width) or [""]:
            lines.append(" " * ind + part)
        prev = typ
    return lines


def paginate(lines: list[str], per_page: int = 50, title: str = "LE PHARE - Version bleue") -> list[list[str]]:
    pages = []
    for k in range(0, len(lines), per_page):
        chunk = lines[k:k + per_page]
        header = [title + " " * 20 + f"{len(pages) + 1}.", ""]
        pages.append(header + chunk)
    return pages


def to_txt(sp: Screenplay) -> bytes:
    pages = paginate(layout_lines(sp), 30)
    return "\f".join("\n".join(p) for p in pages).encode("cp1252")


def to_pdf(sp: Screenplay, per_page: int = 50) -> bytes:
    pages = paginate(layout_lines(sp), per_page)
    objs: list[bytes] = []

    def add(b: bytes) -> int:
        objs.append(b)
        return len(objs)

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>")
    pages_idx = add(b"")  # rempli plus tard
    kids = []
    for page in pages:
        ops = ["BT", f"/F1 12 Tf"]
        y = 750
        for ln in page:
            if ln.strip():
                s = ln.encode("cp1252", "replace").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
                ops.append(f"1 0 0 1 {72 + 7.2 * (len(ln) - len(ln.lstrip()))} {y} Tm")
                ops.append("(" + s.decode("latin-1").lstrip() + ") Tj")
            y -= 12
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                        b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (pages_idx, content, font)))
    objs[pages_idx - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_idx)
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % i + o + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1))
    for off in offsets:
        out.write(b"%010d 00000 n \n" % off)
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref))
    return out.getvalue()
