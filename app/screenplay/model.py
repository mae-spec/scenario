"""Modèle de données d'un scénario, indépendant du format source."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Types d'éléments bruts produits par les parseurs, avant regroupement en unités.
ELEMENT_TYPES = {
    "heading",
    "action",
    "character",
    "dialogue",
    "parenthetical",
    "transition",
    "centered",
    "lyrics",
    "section",
    "synopsis",
    "page_break",
}


@dataclass
class Element:
    type: str
    text: str
    scene_number: str = ""
    dual: bool = False


@dataclass
class Unit:
    """Plus petit bloc comparé : un paragraphe d'action, une réplique, une transition."""

    kind: str  # action | dialogue | transition
    text: str
    character: str = ""  # nom normalisé (répliques uniquement)
    extension: str = ""  # V.O., OFF, O.S. ...
    dual: bool = False
    parts: list = field(default_factory=list)  # [{"type": "paren"|"line", "text": str}]

    @classmethod
    def from_dict(cls, d: dict) -> "Unit":
        return cls(**d)


@dataclass
class Scene:
    heading: str
    number: str = ""
    prologue: bool = False
    sections: list = field(default_factory=list)
    units: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        d = dict(d)
        d["units"] = [Unit.from_dict(u) for u in d.get("units", [])]
        return cls(**d)


@dataclass
class Screenplay:
    source_format: str
    title_page: dict = field(default_factory=dict)
    scenes: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Screenplay":
        return cls(
            source_format=d.get("source_format", ""),
            title_page=d.get("title_page", {}),
            scenes=[Scene.from_dict(s) for s in d.get("scenes", [])],
            warnings=list(d.get("warnings", [])),
        )
