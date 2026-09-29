"""Stockage local : SQLite + fichiers originaux dans le dossier de données."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .screenplay import PARSER_VERSION, ParseError, Screenplay, detect_format, parse_file, screenplay_stats

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    doc_date TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    fmt TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    position INTEGER NOT NULL,
    created_at REAL NOT NULL,
    parser_version INTEGER NOT NULL,
    parsed TEXT NOT NULL,
    stats TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_project ON versions(project_id, position);
"""

VERSION_COLS = ("id, project_id, label, notes, doc_date, filename, fmt, sha256, size, position, "
                "created_at, parser_version, stats")


class NotFound(Exception):
    pass


class Store:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.files_dir = self.data_dir / "files"
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.data_dir / "scenario.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- utilitaires -------------------------------------------------------
    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    def _x(self, sql: str, args: tuple = ()) -> int:
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur.lastrowid

    @staticmethod
    def _version_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["stats"] = json.loads(d.get("stats") or "{}")
        d.pop("parser_version", None)
        return d

    # -- projets -----------------------------------------------------------
    def list_projects(self) -> list[dict]:
        rows = self._q(
            "SELECT p.*, COUNT(v.id) AS versions, MAX(v.created_at) AS last_version_at "
            "FROM projects p LEFT JOIN versions v ON v.project_id = p.id "
            "GROUP BY p.id ORDER BY p.updated_at DESC"
        )
        return [dict(r) for r in rows]

    def get_project(self, pid: int) -> dict:
        rows = self._q("SELECT * FROM projects WHERE id = ?", (pid,))
        if not rows:
            raise NotFound("Projet introuvable")
        return dict(rows[0])

    def create_project(self, name: str, description: str = "") -> dict:
        now = time.time()
        pid = self._x("INSERT INTO projects(name, description, created_at, updated_at) VALUES (?,?,?,?)",
                      (name.strip(), description.strip(), now, now))
        return self.get_project(pid)

    def update_project(self, pid: int, name: str | None = None, description: str | None = None) -> dict:
        p = self.get_project(pid)
        self._x("UPDATE projects SET name=?, description=?, updated_at=? WHERE id=?",
                ((name if name is not None else p["name"]).strip(),
                 (description if description is not None else p["description"]).strip(), time.time(), pid))
        return self.get_project(pid)

    def delete_project(self, pid: int) -> None:
        self.get_project(pid)
        for v in self._q("SELECT stored_name FROM versions WHERE project_id = ?", (pid,)):
            self._unlink(v["stored_name"])
        self._x("DELETE FROM versions WHERE project_id = ?", (pid,))
        self._x("DELETE FROM projects WHERE id = ?", (pid,))

    def _touch(self, pid: int) -> None:
        self._x("UPDATE projects SET updated_at=? WHERE id=?", (time.time(), pid))

    # -- versions ----------------------------------------------------------
    def list_versions(self, pid: int) -> list[dict]:
        self.get_project(pid)
        rows = self._q(f"SELECT {VERSION_COLS} FROM versions WHERE project_id = ? ORDER BY position, id", (pid,))
        return [self._version_dict(r) for r in rows]

    def get_version(self, vid: int) -> dict:
        rows = self._q(f"SELECT {VERSION_COLS} FROM versions WHERE id = ?", (vid,))
        if not rows:
            raise NotFound("Version introuvable")
        return self._version_dict(rows[0])

    def add_version(self, pid: int, filename: str, data: bytes, label: str = "", notes: str = "",
                    doc_date: str = "") -> dict:
        self.get_project(pid)
        sp = parse_file(filename, data)  # lève ParseError si illisible
        fmt = detect_format(filename, data)
        sha = hashlib.sha256(data).hexdigest()
        stored = f"{uuid.uuid4().hex}.{fmt}"
        tmp = self.files_dir / (stored + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, self.files_dir / stored)
        rows = self._q("SELECT COALESCE(MAX(position), 0) AS m, COUNT(*) AS n FROM versions WHERE project_id = ?",
                       (pid,))
        position = rows[0]["m"] + 1
        label = label.strip() or f"Version {rows[0]['n'] + 1}"
        vid = self._x(
            "INSERT INTO versions(project_id, label, notes, doc_date, filename, stored_name, fmt, sha256, size, "
            "position, created_at, parser_version, parsed, stats) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, label, notes.strip(), doc_date.strip(), os.path.basename(filename) or "document", stored, fmt,
             sha, len(data), position, time.time(), PARSER_VERSION, json.dumps(sp.to_dict(), ensure_ascii=False),
             json.dumps(self._stats(sp), ensure_ascii=False)),
        )
        self._touch(pid)
        return self.get_version(vid)

    def find_duplicate(self, pid: int, data: bytes) -> dict | None:
        sha = hashlib.sha256(data).hexdigest()
        rows = self._q(f"SELECT {VERSION_COLS} FROM versions WHERE project_id = ? AND sha256 = ?", (pid, sha))
        return self._version_dict(rows[0]) if rows else None

    @staticmethod
    def _stats(sp: Screenplay) -> dict:
        st = screenplay_stats(sp)
        st["warnings"] = sp.warnings
        return st

    def update_version(self, vid: int, **fields) -> dict:
        v = self.get_version(vid)
        allowed = {k: (fields[k] or "").strip() for k in ("label", "notes", "doc_date") if fields.get(k) is not None}
        if allowed:
            sets = ", ".join(f"{k}=?" for k in allowed)
            self._x(f"UPDATE versions SET {sets} WHERE id=?", (*allowed.values(), vid))
        if fields.get("move") in ("up", "down"):
            self._move(v, fields["move"])
        self._touch(v["project_id"])
        return self.get_version(vid)

    def _move(self, v: dict, direction: str) -> None:
        versions = self.list_versions(v["project_id"])
        idx = next(i for i, x in enumerate(versions) if x["id"] == v["id"])
        other = idx - 1 if direction == "up" else idx + 1
        if not 0 <= other < len(versions):
            return
        versions[idx], versions[other] = versions[other], versions[idx]
        with self._lock:
            for pos, x in enumerate(versions, start=1):
                self.db.execute("UPDATE versions SET position=? WHERE id=?", (pos, x["id"]))
            self.db.commit()

    def delete_version(self, vid: int) -> None:
        rows = self._q("SELECT stored_name, project_id FROM versions WHERE id = ?", (vid,))
        if not rows:
            raise NotFound("Version introuvable")
        self._unlink(rows[0]["stored_name"])
        self._x("DELETE FROM versions WHERE id = ?", (vid,))
        self._touch(rows[0]["project_id"])

    def original(self, vid: int) -> tuple[str, Path]:
        rows = self._q("SELECT filename, stored_name FROM versions WHERE id = ?", (vid,))
        if not rows:
            raise NotFound("Version introuvable")
        return rows[0]["filename"], self.files_dir / rows[0]["stored_name"]

    def screenplay(self, vid: int) -> Screenplay:
        rows = self._q("SELECT filename, stored_name, parser_version, parsed FROM versions WHERE id = ?", (vid,))
        if not rows:
            raise NotFound("Version introuvable")
        r = rows[0]
        if r["parser_version"] != PARSER_VERSION:
            return self.reparse(vid)
        return Screenplay.from_dict(json.loads(r["parsed"]))

    def reparse(self, vid: int) -> Screenplay:
        filename, path = self.original(vid)
        sp = parse_file(filename, path.read_bytes())
        self._x("UPDATE versions SET parsed=?, stats=?, parser_version=? WHERE id=?",
                (json.dumps(sp.to_dict(), ensure_ascii=False), json.dumps(self._stats(sp), ensure_ascii=False),
                 PARSER_VERSION, vid))
        return sp

    def _unlink(self, stored_name: str) -> None:
        p = self.files_dir / stored_name
        try:
            p.unlink()
        except FileNotFoundError:
            pass


__all__ = ["Store", "NotFound", "ParseError"]
