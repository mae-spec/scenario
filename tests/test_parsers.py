import pytest

from app.compare.engine import compare
from app.screenplay import parse_file
from app.screenplay.export import to_fountain
from app.screenplay.parsers import ParseError, parse_fountain, parse_text
from app.screenplay.rules import heading_parts, parse_heading, split_character
from tests import builders as B


def test_fountain_structure(v1):
    assert v1.title_page["title"] == "Le Phare"
    heads = [s.heading for s in v1.scenes]
    assert heads == ["INT. CUISINE - JOUR", "EXT. PHARE - NUIT", "EXT. PLAGE - AUBE", "INT. BUREAU DU MAIRE - JOUR"]
    first = v1.scenes[0].units
    assert [u.kind for u in first] == ["action", "action", "dialogue", "dialogue", "dialogue", "dialogue", "transition"]
    assert first[2].character == "PAUL"
    assert first[2].parts[0] == {"type": "paren", "text": "(bâillant)"}
    assert v1.scenes[1].units[1].extension == "V.O."


@pytest.mark.parametrize("line,ok,text,num", [
    ("INT. CUISINE - JOUR", True, "INT. CUISINE - JOUR", ""),
    ("12 EXT. RUE - NUIT 12", True, "EXT. RUE - NUIT", "12"),
    ("12A. INT./EXT. VOITURE - JOUR", True, "INT./EXT. VOITURE - JOUR", "12A"),
    ("SÉQ. 4 - INT. GARE - MATIN", True, "INT. GARE - MATIN", "4"),
    ("3. CUISINE - INT. JOUR", True, "CUISINE - INT. JOUR", "3"),
    ("INTÉRIEUR SALON - SOIR", True, "INTÉRIEUR SALON - SOIR", ""),
    ("INT. BUREAU - JOUR #7#", True, "INT. BUREAU - JOUR", "7"),
    ("Intérieurement, il sourit.", False, None, None),
    ("EXTRA ! EXTRA !", False, None, None),
])
def test_parse_heading(line, ok, text, num):
    got = parse_heading(line)
    assert got[0] is ok
    if ok:
        assert got[1] == text and got[2] == num


def test_heading_parts():
    p = heading_parts("INT. BUREAU DU MAIRE - JOUR")
    assert p == {"int_ext": "INT", "location": "BUREAU DU MAIRE", "time": "JOUR"}


def test_split_character():
    assert split_character("PAUL (V.O.)") == ("PAUL", "V.O.", False, False)
    assert split_character("MARIE (CONT'D)") == ("MARIE", "", False, True)
    assert split_character("@McCLANE ^") == ("MCCLANE", "", True, False)
    assert split_character("JEAN (SUITE)")[3] is True
    assert split_character("LÉA - OFF") == ("LÉA", "OFF", False, False)


def test_fountain_features():
    sp = parse_fountain(
        "INT. SALON - NUIT\n\n/* ancienne version */\nIl pleut. [[note]]\n\n"
        "!TOUT EN MAJUSCULES\n\n@McCLANE\nYippee.\n\n.FLASHBACK\n\n> FONDU AU NOIR.\n\n# Acte II\n\n"
        "EXT. RUE - JOUR\n\n**Gras** et _souligné_.\n"
    )
    units = sp.scenes[0].units
    assert units[0].text == "Il pleut."
    assert units[1].kind == "action" and units[1].text == "TOUT EN MAJUSCULES"
    assert units[2].character == "MCCLANE"
    assert sp.scenes[1].heading == "FLASHBACK"
    assert sp.scenes[1].units[0].kind == "transition"
    assert sp.scenes[2].sections == []
    assert "Acte II" in sp.scenes[1].sections
    assert sp.scenes[2].units[0].text == "Gras et souligné."


def test_dialogue_continuation_merged():
    sp = parse_text(
        "INT. SALON - NUIT\n\n          MARIE\n     Je commence une phrase\n     (MORE)\n\f"
        "          MARIE (CONT'D)\n     et je la termine.\n"
    )
    units = sp.scenes[0].units
    assert len(units) == 1
    assert units[0].text == "Je commence une phrase\net je la termine."


def test_inline_dialogue_format():
    txt = "INT. SALON - NUIT\n\nMARIE : Bonjour.\nPAUL : Salut.\nMARIE : Ça va ?\nPAUL (off) : Oui.\n"
    units = parse_text(txt).scenes[0].units
    assert [u.character for u in units] == ["MARIE", "PAUL", "MARIE", "PAUL"]
    assert units[3].extension == "OFF"


def test_no_heading_warning():
    sp = parse_text("Juste un texte.\n\nSans séquence.\n")
    assert sp.warnings


@pytest.mark.parametrize("fmt", ["fdx", "docx", "docx-nostyle", "docx-blank", "odt", "txt", "pdf13", "pdf20", "pdf50"])
@pytest.mark.parametrize("which", ["v1", "v2"])
def test_all_formats_round_trip(fmt, which, request):
    src = request.getfixturevalue(which)
    makers = {
        "fdx": (B.to_fdx, "fdx"), "docx": (B.to_docx, "docx"),
        "docx-nostyle": (lambda s: B.to_docx(s, False), "docx"),
        "docx-blank": (lambda s: B.to_docx(s, False, True), "docx"),
        "odt": (B.to_odt, "odt"), "txt": (B.to_txt, "txt"),
        "pdf13": (lambda s: B.to_pdf(s, 13), "pdf"), "pdf20": (lambda s: B.to_pdf(s, 20), "pdf"),
        "pdf50": (lambda s: B.to_pdf(s, 50), "pdf"),
    }
    fn, ext = makers[fmt]
    sp = parse_file(f"script.{ext}", fn(src))
    result = compare(src, sp)
    assert result["summary"]["identical"], [
        (u["status"], u["text"]) for s in result["scenes"] for u in s["units"] if u["status"] != "unchanged"]


def test_fountain_export_round_trip(v2):
    again = parse_fountain(to_fountain(v2))
    assert compare(v2, again)["summary"]["identical"]


def test_detect_by_content():
    sp = parse_file("sans_extension", B.to_fdx(parse_fountain("INT. A - JOUR\n\nTexte.\n")))
    assert sp.source_format == "fdx"


def test_xml_entities_rejected():
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><FinalDraft><Content/></FinalDraft>'
    with pytest.raises(ParseError):
        parse_file("x.fdx", evil)


def test_invalid_pdf():
    with pytest.raises(ParseError):
        parse_file("x.pdf", b"%PDF-1.4 garbage")


def test_encodings():
    text = "INT. CAFÉ - JOUR\n\nLéa entre.\n"
    for enc in ("utf-8", "cp1252", "utf-16"):
        sp = parse_file("a.txt", text.encode(enc))
        assert sp.scenes[0].heading == "INT. CAFÉ - JOUR"
        assert sp.scenes[0].units[0].text == "Léa entre."


@pytest.mark.parametrize("line", ["est bleu.", "Est-ce que tu viens ?", "Intérieur du camion : rien.", "Exténué, il dort."])
def test_not_headings(line):
    assert parse_heading(line)[0] is False


@pytest.mark.parametrize("line", ["int. maison - jour", "ext. rue - nuit", "int./ext. voiture - jour", "EST. PARIS - JOUR"])
def test_lowercase_headings(line):
    assert parse_heading(line)[0] is True
