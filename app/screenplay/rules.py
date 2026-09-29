"""Règles de reconnaissance des éléments d'un scénario (FR + EN)."""
from __future__ import annotations

import re
import unicodedata

UPPER_LETTERS = "A-ZÀÂÄÆÇÉÈÊËÎÏÔŒÖÙÛÜŸÑÁÍÓÚ"

_PREFIX = (
    r"INT\.?\s*[/\-–]\s*EXT|EXT\.?\s*[/\-–]\s*INT|I\s*/\s*E|INT[ÉE]RIEURE?|EXT[ÉE]RIEURE?"
    r"|INT|EXT|EST"
)
_NUM_PREFIX = r"(?:(?:S[ÉE]Q(?:UENCE)?|SC[ÈE]NE|SC)\.?\s*)?(?P<num>\d{1,4}[A-Z]{0,2})\s*(?:[.):\-–—]\s*|\s+)"

# Forme classique : [12.] INT. CUISINE - JOUR [12]
HEADING_RE = re.compile(
    rf"^(?:{_NUM_PREFIX})?(?P<prefix>{_PREFIX})(?:\.|\s|:|\-|–|—|/)\s*\S",
    re.IGNORECASE,
)
# Forme « française » : 12. CUISINE - INT. JOUR / CUISINE – INT/NUIT
TIME_WORDS = (
    "JOUR", "NUIT", "SOIR", "SOIREE", "MATIN", "AUBE", "AURORE", "CREPUSCULE", "MIDI",
    "APRES-MIDI", "FIN DE JOURNEE", "DAY", "NIGHT", "MORNING", "EVENING", "DAWN", "DUSK",
    "CONTINUOUS", "LATER", "CONTINU", "PLUS TARD", "MEME MOMENT", "SUITE",
)
_ALT_HEADING_RE = re.compile(r"\b(INT|EXT|INTERIEURE?|EXTERIEURE?)\b\.?", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in TIME_WORDS) + r")\b")

TRANSITION_RE = re.compile(
    r"^(?:[" + UPPER_LETTERS + r"\s.'’\-]+\sTO:"
    r"|FADE (?:IN|OUT|TO BLACK)[.:]?"
    r"|CUT TO BLACK[.:]?|SMASH CUT.*|MATCH CUT.*|JUMP CUT.*"
    r"|FONDU(?: AU NOIR| AU BLANC| ENCHA[ÎI]N[ÉE]| AU| EN OUVERTURE| EN FERMETURE)?(?: .{0,20})?\s*[.:]?"
    r"|OUVERTURE AU NOIR\s*[.:]?|FERMETURE AU NOIR\s*[.:]?"
    r"|COUPE(?: FRANCHE| S[ÈE]CHE)?\s*[.:]?|CUT\s*[.:]?"
    r"|ENCHA[ÎI]N[ÉE]E?\s*[.:]?|RACCORD.{0,20}:"
    r"|NOIR\s*[.:]?|FIN\s*[.:]?|THE END\s*[.:]?)$"
)

# Marques de continuité à ignorer dans les noms de personnages
CONTINUATION_EXT_RE = re.compile(r"^(?:CONT['’]?D|CONT\.?|CONTINUED|SUITE|CONT['’]?D\.?|CONTINUING)$", re.I)

# Artefacts de mise en page (sauts de page) à supprimer des extractions texte/PDF
PAGE_ARTIFACT_RE = re.compile(
    r"^\s*(?:\((?:MORE|PLUS|SUITE|[ÀA] SUIVRE|CONTINUED|CONT['’]?D)\)|CONTINUED:?|\(?CONTINUED\)?:?"
    r"|SUITE\s*:|\(SUITE\)\s*:?)\s*$",
    re.IGNORECASE,
)
PAGE_NUMBER_RE = re.compile(r"^\s*(?:(?:page|p\.)\s*)?[-–]?\s*\d{1,4}\s*[-–]?\s*\.?\s*(?:/\s*\d{1,4})?\s*$", re.I)
REVISION_MARK_RE = re.compile(r"\s+\*+\s*$")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


_TYPO_TABLE = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u201c": '"', "\u201d": '"', "\u00ab": '"', "\u00bb": '"',
    "\u2026": "...", "\u2013": "-", "\u2014": "-", "\u00a0": " ", "\u202f": " ", "\u2009": " ",
    "\u0153": "oe", "\u0152": "OE",
})


def normalize_typography(s: str) -> str:
    """Neutralise les variantes typographiques qui ne changent pas le sens."""
    return s.translate(_TYPO_TABLE)


def is_upper_text(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and all(not c.islower() for c in letters)


def parse_heading(line: str) -> tuple[bool, str, str]:
    """Retourne (est_un_entête, texte_sans_numéro, numéro)."""
    s = REVISION_MARK_RE.sub("", line.strip())
    if not s or len(s) > 120:
        return False, s, ""
    number = ""
    # Numéro fountain : INT. CUISINE - JOUR #12#
    m = re.search(r"\s*#([\w.\-]+)#\s*$", s)
    if m:
        number = m.group(1)
        s = s[: m.start()].rstrip()
    m = HEADING_RE.match(s)
    if m and not is_upper_text(s):
        # En minuscules, seule la forme abrégée « int. » / « ext. » est acceptée
        # (évite « Est-ce que… », « Intérieur du camion : … »).
        after = s[m.end("prefix"):m.end("prefix") + 1]
        short = re.fullmatch(r"(?:INT|EXT)(?:\.?\s*[/\-–]\s*(?:INT|EXT))?|I\s*/\s*E", m.group("prefix"), re.I)
        if not (short and (after == "." or m.group("prefix").endswith(("T", "t", "E", "e")) and "/" in m.group("prefix"))):
            m = None
    ok = False
    if m:
        ok = True
        if m.group("num"):
            number = number or m.group("num")
            s = s[m.start("prefix"):]
    else:
        up = strip_accents(s).upper()
        if is_upper_text(s) and _ALT_HEADING_RE.search(up) and _TIME_RE.search(up) and len(s.split()) <= 14:
            ok = True
            m2 = re.match(_NUM_PREFIX, s, re.I)
            if m2:
                number = number or m2.group("num")
                s = s[m2.end():]
    if not ok:
        return False, s, number
    # Numéro répété en fin de ligne (export PDF) : INT. CUISINE - JOUR   12
    m = re.search(r"\s+(\d{1,4}[A-Z]{0,2})\s*$", s)
    if m and (not number or m.group(1) == number):
        number = number or m.group(1)
        s = s[: m.start()].rstrip()
    return True, s.strip(), number


def normalize_heading(heading: str) -> str:
    s = strip_accents(normalize_typography(heading)).upper()
    s = re.sub(r"[^\w]+", " ", s)
    s = re.sub(r"\bINTERIEURE?\b", "INT", s)
    s = re.sub(r"\bEXTERIEURE?\b", "EXT", s)
    return re.sub(r"\s+", " ", s).strip()


def heading_parts(heading: str) -> dict:
    """Découpe un entête en INT/EXT, lieu et moment (au mieux)."""
    norm = normalize_heading(heading)
    ie = ""
    if re.search(r"\bINT\b.*\bEXT\b|\bEXT\b.*\bINT\b|\bI E\b", norm):
        ie = "INT/EXT"
    elif re.search(r"\bINT\b", norm):
        ie = "INT"
    elif re.search(r"\bEXT\b|\bEST\b", norm):
        ie = "EXT"
    raw = strip_accents(normalize_typography(heading)).upper()
    segments = [p.strip(" .") for p in re.split(r"\s+[-/]\s+|\s*[-]\s+|\s+-\s*", raw) if p.strip(" .")]
    time = ""
    if len(segments) > 1 and _TIME_RE.search(segments[-1]):
        time = segments[-1]
        segments = segments[:-1]
    loc = " - ".join(segments)
    loc = re.sub(r"^(INT\.?\s*[/\-]\s*EXT|EXT\.?\s*[/\-]\s*INT|I\s*/\s*E|INTERIEURE?|EXTERIEURE?|INT|EXT|EST)\b\.?\s*", "", loc)
    return {"int_ext": ie, "location": loc.strip(" .-/") or "", "time": time}


def is_transition(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 40 or not is_upper_text(s):
        return False
    return bool(TRANSITION_RE.match(s))


_CHAR_ALLOWED_RE = re.compile(r"^[\w .'’\-&#/]+$")


def split_character(raw: str) -> tuple[str, str, bool, bool]:
    """Retourne (nom normalisé, extension, dual, est_une_suite)."""
    s = raw.strip()
    dual = s.endswith("^")
    s = s.rstrip("^").strip()
    if s.startswith("@"):
        s = s[1:]
    exts = [e.strip() for e in re.findall(r"\(([^)]*)\)", s)]
    name = re.sub(r"\([^)]*\)", " ", s)
    name = re.sub(r"\s+", " ", name).strip().rstrip(":").strip()
    continuation = any(CONTINUATION_EXT_RE.match(e) for e in exts)
    ext = ", ".join(e.upper() for e in exts if e and not CONTINUATION_EXT_RE.match(e))
    # « JEAN (V.O.) » mais aussi « JEAN - OFF » / « JEAN, OFF »
    m = re.match(r"^(.*?)\s*(?:,|\s-)\s*(OFF|IN|V\.?O\.?|O\.?S\.?|H\.?C\.?|OS)$", name, re.I)
    if m:
        name = m.group(1).strip()
        ext = ", ".join(x for x in [ext, m.group(2).upper()] if x)
    return name.upper(), ext, dual, continuation


def looks_like_character(line: str, forced: bool = False) -> bool:
    s = line.strip()
    if forced:
        return bool(s)
    if not s or len(s) > 50:
        return False
    base = re.sub(r"\([^)]*\)", "", s).rstrip("^").strip().rstrip(":").strip()
    if not base or not any(c.isalpha() for c in base):
        return False
    if not is_upper_text(base):
        return False
    if len(base.split()) > 5:
        return False
    if base[-1] in ".!?,;…" and not re.search(r"\b(?:M|MR|MME|DR|ST|STE|MLLE|MRS|MS)\.$", base):
        return False
    if not _CHAR_ALLOWED_RE.match(base):
        return False
    if parse_heading(s)[0] or is_transition(s):
        return False
    return True
